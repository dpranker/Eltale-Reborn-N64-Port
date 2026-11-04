#!/usr/bin/env python3
"""Walks an F3DEX 1.23 display list the way the RSP would, reports anything real hardware won't accept, and estimates
the pixel work that ares doesn't time.

Limits come from the microcode's GBI: a 32-vertex buffer, 18 levels of nested display lists, 4 KB of TMEM. A matrix
stack holds dram_stack_size / 64 matrices.

The pixel estimate transforms and clips each triangle and adds up screen area, with no occlusion. Costs are the RDP's
best case in clocks per pixel, so they ignore memory latency: useful for comparing frames, not a frame time.
"""

import struct

VERTEX_BUFFER = 32
DL_DEPTH = 18
TMEM_BYTES = 4096
MAX_COMMANDS = 200000
RDP_CLOCKS_PER_FRAME = 62_500_000 * 2 / 59.94  # A 30 fps frame.
SAFE = (8, 8, 312, 232)  # Inside the 8-pixel margins the game's 3D scissor keeps, and that a display's overscan can hide.
LARGE_RECT = (300, 200)  # At least this wide or tall: a background or a fade, which is meant to reach the edge.

G_SPNOOP, G_MTX, G_MOVEMEM, G_VTX, G_DL = 0x00, 0x01, 0x03, 0x04, 0x06
G_TRI2, G_MODIFYVTX, G_RDPHALF_2, G_RDPHALF_1, G_QUAD = 0xB1, 0xB2, 0xB3, 0xB4, 0xB5
G_CLEARGEOMETRYMODE, G_SETGEOMETRYMODE, G_ENDDL, G_SETOTHERMODE_L, G_SETOTHERMODE_H = 0xB6, 0xB7, 0xB8, 0xB9, 0xBA
G_TEXTURE, G_MOVEWORD, G_POPMTX, G_CULLDL, G_TRI1, G_NOOP = 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0
G_TEXRECT, G_TEXRECTFLIP = 0xE4, 0xE5
G_LOADTLUT, G_SETTILESIZE, G_LOADBLOCK, G_LOADTILE, G_SETTILE, G_FILLRECT = 0xF0, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6
G_SETTIMG = 0xFD
G_MV_VIEWPORT = 0x80
G_MW_SEGMENT = 0x06
G_CULL_FRONT, G_CULL_BACK = 0x1000, 0x2000
MTX_PROJECTION, MTX_LOAD, MTX_PUSH = 0x01, 0x02, 0x04
CYCLE_1, CYCLE_2, CYCLE_COPY, CYCLE_FILL = 0, 1, 2, 3
CLOCKS_PER_PIXEL = {CYCLE_1: 1.0, CYCLE_2: 2.0, CYCLE_COPY: 0.25, CYCLE_FILL: 0.25}

KNOWN = {
    G_SPNOOP, G_MTX, G_MOVEMEM, G_VTX, G_DL, G_TRI2, G_MODIFYVTX, G_RDPHALF_2, G_RDPHALF_1, G_QUAD, G_CLEARGEOMETRYMODE,
    G_SETGEOMETRYMODE, G_ENDDL, G_SETOTHERMODE_L, G_SETOTHERMODE_H, G_TEXTURE, G_MOVEWORD, G_POPMTX, G_CULLDL, G_TRI1,
    G_NOOP, G_TEXRECT, G_TEXRECTFLIP,
} | set(range(0xE6, 0x100))
UNKNOWN_RDP = {0xF1}  # The one gap in the RDP's range.
IDENTITY = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def multiply(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def clip_polygon(points, inside, intersect):
    """One Sutherland-Hodgman pass."""
    out = []
    for i, cur in enumerate(points):
        prev = points[i - 1]
        if inside(cur) != inside(prev):
            out.append(intersect(prev, cur))
        if inside(cur):
            out.append(cur)
    return out


def screen_area(clip, viewport, scissor):
    """Signed area in pixels of a clip-space triangle on screen, positive when wound clockwise on screen (y down), and
    0 when nothing of it is visible. The sign comes from the unclipped winding."""
    near = 1e-3

    def cross_near(a, b):
        t = (near - a[3]) / (b[3] - a[3])
        return tuple(a[k] + (b[k] - a[k]) * t for k in range(4))

    poly = clip_polygon(clip, lambda p: p[3] >= near, cross_near)
    if len(poly) < 3:
        return 0.0
    sx, sy, tx, ty = viewport
    pts = [(tx + p[0] / p[3] * sx, ty - p[1] / p[3] * sy) for p in poly]

    def signed(points):
        return sum(points[i - 1][0] * points[i][1] - points[i][0] * points[i - 1][1] for i in range(len(points))) / 2

    sign = signed(pts)
    x0, y0, x1, y1 = scissor
    for axis, edge, keep_above in ((0, x0, True), (0, x1, False), (1, y0, True), (1, y1, False)):
        def inside(p, axis=axis, edge=edge, keep_above=keep_above):
            return p[axis] >= edge if keep_above else p[axis] <= edge

        def cross(a, b, axis=axis, edge=edge):
            t = (edge - a[axis]) / (b[axis] - a[axis])
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

        pts = clip_polygon(pts, inside, cross)
        if len(pts) < 3:
            return 0.0
    area = abs(signed(pts))
    return area if sign >= 0 else -area


class Checker:
    """`read(physical address, size)` returns RDRAM bytes. `owner(address)` can name what an address belongs to."""

    def __init__(self, read, owner=None, matrix_stack=10):
        self.read = read
        self.owner = owner or (lambda address: f"{address:#x}")
        self.matrix_stack = matrix_stack
        self.trace = None
        self.segments = [0] * 16
        self.geometry = 0
        self.other_h = 0
        self.modelview = [IDENTITY]
        self.projection = IDENTITY
        self.mvp = None
        self.viewport = (640 / 4, 480 / 4, 640 / 4, 480 / 4)
        self.scissor = (0.0, 0.0, 320.0, 240.0)
        self.vertices = [None] * VERTEX_BUFFER
        self.timg_size = 2
        self.tiles = [(0, 2) for _ in range(8)]
        self.problems = {}
        self.edge_rects = {}
        self.stats = dict(commands=0, lists=0, deepest=0, vertices=0, triangles=0, off_screen=0, culled=0, drawn=0,
                          pixels=0.0, clocks=0.0, rect_pixels=0.0, texture_loads=0, texture_bytes=0, largest_load=0,
                          two_cycle_pixels=0.0, mod_lists=0)

    def problem(self, kind, where, detail=""):
        key = (kind, self.owner(where), detail)
        self.problems[key] = self.problems.get(key, 0) + 1

    def resolve(self, address):
        return (self.segments[(address >> 24) & 0xF] + (address & 0xFFFFFF)) & 0xFFFFFF

    def cycle_type(self):
        return (self.other_h >> 20) & 3

    def load_matrix(self, address):
        raw = struct.unpack(">16h16H", self.read(address, 64))
        return [[(((raw[i * 4 + j] & 0xFFFF) << 16 | raw[16 + i * 4 + j]) - (1 << 32 if raw[i * 4 + j] < 0 else 0)) / 65536
                 for j in range(4)] for i in range(4)]

    def command_mtx(self, w0, w1, where):
        params = (w0 >> 16) & 0xFF
        matrix = self.load_matrix(self.resolve(w1))
        if params & MTX_PROJECTION:
            self.projection = matrix if params & MTX_LOAD else multiply(matrix, self.projection)
        else:
            if params & MTX_PUSH:
                if len(self.modelview) >= self.matrix_stack:
                    self.problem("matrix stack overflow", where)
                self.modelview.append(self.modelview[-1])
            self.modelview[-1] = matrix if params & MTX_LOAD else multiply(matrix, self.modelview[-1])
        self.mvp = None

    def command_vtx(self, w0, w1, where):
        v0, n = ((w0 >> 16) & 0xFF) // 2, (w0 >> 10) & 0x3F
        if n == 0 or v0 + n > VERTEX_BUFFER:
            self.problem("vertex load outside the 32-entry buffer", where, f"v0={v0} n={n}")
        self.stats["vertices"] += n
        if self.mvp is None:
            self.mvp = multiply(self.modelview[-1], self.projection)
        data = self.read(self.resolve(w1), n * 16)
        m = self.mvp
        for i in range(n):
            x, y, z = struct.unpack_from(">3h", data, i * 16)
            if v0 + i < VERTEX_BUFFER:
                self.vertices[v0 + i] = tuple(x * m[0][k] + y * m[1][k] + z * m[2][k] + m[3][k] for k in range(4))

    def triangle(self, a, b, c, where):
        self.stats["triangles"] += 1
        for index in (a, b, c):
            if index >= VERTEX_BUFFER:
                self.problem("triangle index outside the 32-entry buffer", where, f"index={index}")
                return
        clip = [self.vertices[a], self.vertices[b], self.vertices[c]]
        if None in clip:
            self.problem("triangle uses a vertex never loaded", where)
            return
        area = screen_area(clip, self.viewport, self.scissor)
        if area == 0:
            self.stats["off_screen"] += 1
        elif (area > 0 and self.geometry & G_CULL_BACK) or (area < 0 and self.geometry & G_CULL_FRONT):
            self.stats["culled"] += 1
        else:
            self.stats["drawn"] += 1
            self.add_pixels(abs(area))
            if self.trace is not None:
                self.trace.append((clip, self.viewport, abs(area), self.cycle_type()))

    def add_pixels(self, pixels):
        cycle = self.cycle_type()
        self.stats["pixels"] += pixels
        self.stats["clocks"] += pixels * CLOCKS_PER_PIXEL[cycle]
        if cycle == CYCLE_2:
            self.stats["two_cycle_pixels"] += pixels

    def rectangle(self, w0, w1, where, extra=0):
        lrx, lry = (w0 >> 12) & 0xFFF, w0 & 0xFFF
        ulx, uly = (w1 >> 12) & 0xFFF, w1 & 0xFFF
        x0, y0, x1, y1 = self.scissor
        self.note_edge(ulx / 4, uly / 4, lrx / 4 + extra, lry / 4 + extra, where)
        w = min(lrx / 4 + extra, x1) - max(ulx / 4, x0)
        h = min(lry / 4 + extra, y1) - max(uly / 4, y0)
        if w > 0 and h > 0:
            self.stats["rect_pixels"] += w * h
            self.add_pixels(w * h)

    def note_edge(self, ulx, uly, lrx, lry, where):
        """Records a 2D rectangle that a display's overscan could hide, or that the scissor cuts. Backgrounds and fades are meant to."""
        if lrx - ulx >= LARGE_RECT[0] or lry - uly >= LARGE_RECT[1] or lrx <= ulx or lry <= uly:
            return
        x0, y0, x1, y1 = self.scissor
        clipped = ulx < x0 or uly < y0 or lrx > x1 or lry > y1
        margin = ulx < SAFE[0] or uly < SAFE[1] or lrx > SAFE[2] or lry > SAFE[3]
        if clipped or margin:
            key = (ulx, uly, lrx, lry, self.scissor, clipped, self.owner(where))
            self.edge_rects[key] = self.edge_rects.get(key, 0) + 1

    def texture_load(self, tile, bytes_loaded, where):
        self.stats["texture_loads"] += 1
        self.stats["texture_bytes"] += bytes_loaded
        self.stats["largest_load"] = max(self.stats["largest_load"], bytes_loaded)
        tmem = self.tiles[tile][0] * 8
        if tmem + bytes_loaded > TMEM_BYTES:
            self.problem("texture load past 4 KB of TMEM", where, f"tmem={tmem} bytes={bytes_loaded}")

    def texel_bytes(self, texels):
        return (texels << self.timg_size) // 2 if self.timg_size else texels // 2

    def walk(self, start):
        """Runs a task's display list from its physical address, using an explicit stack as the RSP does."""
        stack = []
        pc = start
        self.stats["lists"] += 1
        while True:
            if self.stats["commands"] > MAX_COMMANDS:
                self.problem("list never ends", pc)
                return
            self.stats["commands"] += 1
            w0, w1 = struct.unpack(">II", self.read(pc, 8))
            where = pc
            pc += 8
            op = w0 >> 24
            if op not in KNOWN or op in UNKNOWN_RDP:
                self.problem("command not in F3DEX 1.23", where, f"{w0:08x} {w1:08x}")
            elif op == G_DL:
                target = self.resolve(w1)
                if not (w0 >> 16) & 0xFF:
                    stack.append(pc)
                    self.stats["deepest"] = max(self.stats["deepest"], len(stack))
                    if len(stack) >= DL_DEPTH:
                        self.problem("display lists nested past 18 levels", where)
                self.stats["lists"] += 1
                if target >= 0x400000:
                    self.stats["mod_lists"] += 1
                pc = target
            elif op == G_ENDDL:
                if not stack:
                    return
                pc = stack.pop()
            elif op == G_MTX:
                self.command_mtx(w0, w1, where)
            elif op == G_POPMTX:
                if len(self.modelview) > 1:
                    self.modelview.pop()
                else:
                    self.problem("matrix stack underflow", where)
                self.mvp = None
            elif op == G_MOVEWORD:
                if w0 & 0xFF == G_MW_SEGMENT:
                    self.segments[((w0 >> 8) & 0xFFFF) // 4 & 0xF] = w1 & 0xFFFFFF
            elif op == G_MOVEMEM:
                if (w0 >> 16) & 0xFF == G_MV_VIEWPORT:
                    vp = struct.unpack(">8h", self.read(self.resolve(w1), 16))
                    self.viewport = (vp[0] / 4, vp[1] / 4, vp[4] / 4, vp[5] / 4)
            elif op == G_VTX:
                self.command_vtx(w0, w1, where)
            elif op == G_TRI1:
                self.triangle(((w1 >> 16) & 0xFF) // 2, ((w1 >> 8) & 0xFF) // 2, (w1 & 0xFF) // 2, where)
            elif op == G_TRI2:
                self.triangle(((w0 >> 16) & 0xFF) // 2, ((w0 >> 8) & 0xFF) // 2, (w0 & 0xFF) // 2, where)
                self.triangle(((w1 >> 16) & 0xFF) // 2, ((w1 >> 8) & 0xFF) // 2, (w1 & 0xFF) // 2, where)
            elif op == G_QUAD:
                a, b, c, d = (w1 >> 24) // 2, ((w1 >> 16) & 0xFF) // 2, ((w1 >> 8) & 0xFF) // 2, (w1 & 0xFF) // 2
                self.triangle(a, b, c, where)
                self.triangle(a, c, d, where)
            elif op == G_SETGEOMETRYMODE:
                self.geometry |= w1
            elif op == G_CLEARGEOMETRYMODE:
                self.geometry &= ~w1
            elif op == G_SETOTHERMODE_H:
                shift, length = (w0 >> 8) & 0xFF, w0 & 0xFF
                mask = ((1 << length) - 1) << shift
                self.other_h = (self.other_h & ~mask) | (w1 & mask)
            elif op == 0xED:  # G_SETSCISSOR
                self.scissor = (((w0 >> 12) & 0xFFF) / 4, (w0 & 0xFFF) / 4, ((w1 >> 12) & 0xFFF) / 4, (w1 & 0xFFF) / 4)
            elif op == G_FILLRECT:
                self.rectangle(w0, w1, where, 1 if self.cycle_type() >= CYCLE_COPY else 0)
            elif op in (G_TEXRECT, G_TEXRECTFLIP):
                self.rectangle(w0, w1, where, 1 if self.cycle_type() == CYCLE_COPY else 0)
                pc += 16  # G_RDPHALF_1 and G_RDPHALF_2 carry the rest of the command.
            elif op == G_SETTIMG:
                self.timg_size = (w0 >> 19) & 3
                if self.resolve(w1) >= 0x800000:
                    self.problem("texture address outside 8 MB", where, f"{w1:08x}")
            elif op == G_SETTILE:
                self.tiles[(w1 >> 24) & 7] = (w0 & 0x1FF, (w0 >> 19) & 3)
            elif op == G_LOADBLOCK:
                self.texture_load((w1 >> 24) & 7, self.texel_bytes(((w1 >> 12) & 0xFFF) + 1), where)
            elif op == G_LOADTILE:
                columns = (((w1 >> 12) & 0xFFF) - ((w0 >> 12) & 0xFFF)) // 4 + 1
                rows = ((w1 & 0xFFF) - (w0 & 0xFFF)) // 4 + 1
                self.texture_load((w1 >> 24) & 7, self.texel_bytes(columns * rows), where)
            elif op == G_LOADTLUT:
                count = ((w1 >> 14) & 0x3FF) + 1
                self.texture_load((w1 >> 24) & 7, count * 8, where)

    def summary(self):
        stats = dict(self.stats)
        stats["rdp_best_case_percent"] = stats["clocks"] / RDP_CLOCKS_PER_FRAME * 100
        stats["problems"] = [{"kind": k, "at": o, "detail": d, "count": n} for (k, o, d), n in sorted(self.problems.items())]
        stats["edge_rects"] = [dict(rect=k[:4], scissor=k[4], clipped=k[5], at=k[6], count=n) for k, n in sorted(self.edge_rects.items())]
        return stats
