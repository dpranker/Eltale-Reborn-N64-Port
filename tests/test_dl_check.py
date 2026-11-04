#!/usr/bin/env python3
"""Checks tools/dl_check.py on hand-built display lists, so a clean report on a real frame means something."""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import dl_check as dl

failures = 0


def check(ok, text):
    global failures
    print(("ok: " if ok else "FAIL: ") + text)
    failures += not ok


class Memory:
    def __init__(self):
        self.data = bytearray(0x10000)
        self.top = 0x1000

    def put(self, raw):
        at = self.top
        self.data[at:at + len(raw)] = raw
        self.top = (at + len(raw) + 15) & ~15
        return at

    def read(self, address, size):
        return bytes(self.data[address:address + size])

    def words(self, *commands):
        return self.put(b"".join(struct.pack(">II", a, b) for a, b in commands))

    def matrix(self, rows):
        whole = [int(v * 65536) & 0xFFFFFFFF for row in rows for v in row]
        return self.put(struct.pack(">16H16H", *[v >> 16 for v in whole], *[v & 0xFFFF for v in whole]))

    def vertices(self, *points):
        return self.put(b"".join(struct.pack(">3hxxxxxxxxxx", *p) for p in points))


END = (dl.G_ENDDL << 24, 0)


def vtx(address, n, v0=0):
    return ((dl.G_VTX << 24) | (v0 * 2 << 16) | (n << 10) | (n * 16 - 1), address)


def tri(a, b, c):
    return (dl.G_TRI1 << 24, a * 2 << 16 | b * 2 << 8 | c * 2)


def run(memory, start):
    checker = dl.Checker(memory.read)
    checker.walk(start)
    return checker.summary()


def kinds(result):
    return {p["kind"] for p in result["problems"]}


# Identity matrices: x and y map straight to clip space, w = 1, and the default viewport is 320x240 centred.
m = Memory()
square = m.vertices((-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0))
# Half the screen in a triangle: 320 * 240 / 2.
r = run(m, m.words(vtx(square, 4), tri(0, 1, 2), END))
check(not r["problems"], "a plain list has no problems")
check(abs(r["pixels"] - 38400) < 1, f"a half-screen triangle covers 38,400 pixels: {r['pixels']:.0f}")
check(abs(r["clocks"] - 38400) < 1, "one-cycle pixels cost one clock each")

# Winding and culling. On screen y runs down, so this counter-clockwise triangle is front facing.
r = run(m, m.words((dl.G_SETGEOMETRYMODE << 24, dl.G_CULL_BACK), vtx(square, 4), tri(0, 1, 2), END))
check(r["drawn"] == 1, "cull back keeps a counter-clockwise triangle")
r = run(m, m.words((dl.G_SETGEOMETRYMODE << 24, dl.G_CULL_BACK), vtx(square, 4), tri(0, 2, 1), END))
check(r["culled"] == 1 and r["pixels"] == 0, "cull back drops a clockwise triangle")

# Off screen, and a triangle half across the screen edge.
off = m.vertices((5, 5, 0), (6, 5, 0), (6, 6, 0))
r = run(m, m.words(vtx(off, 3), tri(0, 1, 2), END))
check(r["off_screen"] == 1, "a triangle past the edge is off screen")
edge = m.vertices((0, -1, 0), (2, -1, 0), (0, 1, 0))
r = run(m, m.words(vtx(edge, 3), tri(0, 1, 2), END))
check(abs(r["pixels"] - 160 * 240 * 3 / 4) < 1, f"clipping to the screen edge: {r['pixels']:.0f}")

# Cycle types.
two = (dl.G_SETOTHERMODE_H << 24 | 20 << 8 | 2, dl.CYCLE_2 << 20)
r = run(m, m.words(two, vtx(square, 4), tri(0, 1, 2), END))
check(abs(r["clocks"] - 76800) < 1, "two-cycle pixels cost two clocks")
fill = (dl.G_SETOTHERMODE_H << 24 | 20 << 8 | 2, dl.CYCLE_FILL << 20)
rect = (dl.G_FILLRECT << 24 | (319 * 4) << 12 | (239 * 4), 0)
r = run(m, m.words(fill, rect, END))
check(abs(r["pixels"] - 76800) < 1 and abs(r["clocks"] - 19200) < 1, f"a fill rectangle is inclusive and fast: {r['pixels']:.0f}")

# A matrix: scale by a half, then a push and a pop to restore it.
half = m.matrix([[0.5, 0, 0, 0], [0, 0.5, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
load = (dl.G_MTX << 24 | (dl.MTX_LOAD | dl.MTX_PUSH) << 16 | 64, half)
r = run(m, m.words(load, vtx(square, 4), tri(0, 1, 2), (dl.G_POPMTX << 24, 0), vtx(square, 4), tri(0, 1, 2), END))
check(abs(r["pixels"] - (9600 + 38400)) < 1, f"a matrix scales, and a pop restores: {r['pixels']:.0f}")

# Perspective: w = 2 halves the size.
far = m.matrix([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 2]])
load = (dl.G_MTX << 24 | (dl.MTX_LOAD | dl.MTX_PROJECTION) << 16 | 64, far)
r = run(m, m.words(load, vtx(square, 4), tri(0, 1, 2), END))
check(abs(r["pixels"] - 9600) < 1, f"the projection matrix divides by w: {r['pixels']:.0f}")
# A triangle crossing the near plane mustn't blow up.
near = m.matrix([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 1], [0, 0, 0, 0]])
behind = m.vertices((-1, -1, 1), (1, -1, 1), (0, 1, -1))
load = (dl.G_MTX << 24 | (dl.MTX_LOAD | dl.MTX_PROJECTION) << 16 | 64, near)
r = run(m, m.words(load, vtx(behind, 3), tri(0, 1, 2), END))
check(0 <= r["pixels"] <= 76800, f"near-plane clipping stays on screen: {r['pixels']:.0f}")

# Segments and nested lists.
inner = m.words(vtx(square, 4), tri(0, 1, 2), END)
segment = (dl.G_MOVEWORD << 24 | (5 * 4) << 8 | dl.G_MW_SEGMENT, inner - 0x10)
r = run(m, m.words(segment, (dl.G_DL << 24, 0x05000010), END))
check(r["drawn"] == 1 and r["deepest"] == 1, "a segmented call runs the list and returns")
branch = m.words((dl.G_DL << 24 | 1 << 16, inner), (0xFF000000 ^ 0x0E000000, 0))
r = run(m, branch)
check(r["drawn"] == 1 and r["deepest"] == 0 and not r["problems"], "a branch doesn't return to what follows it")

# Everything the checker has to catch.
r = run(m, m.words((0x64 << 24, 0), END))
check("command not in F3DEX 1.23" in kinds(r), "an RT64 command is caught")
r = run(m, m.words((0xF1 << 24, 0), END))
check("command not in F3DEX 1.23" in kinds(r), "the gap in the RDP range is caught")
r = run(m, m.words(vtx(square, 4, v0=30), END))
check("vertex load outside the 32-entry buffer" in kinds(r), "a vertex load past the buffer is caught")
r = run(m, m.words(tri(0, 1, 40), END))
check("triangle index outside the 32-entry buffer" in kinds(r), "a triangle index past the buffer is caught")
r = run(m, m.words(tri(0, 1, 2), END))
check("triangle uses a vertex never loaded" in kinds(r), "a triangle with no vertices is caught")
r = run(m, m.words((dl.G_POPMTX << 24, 0), END))
check("matrix stack underflow" in kinds(r), "a pop with nothing pushed is caught")
push = (dl.G_MTX << 24 | (dl.MTX_LOAD | dl.MTX_PUSH) << 16 | 64, half)
r = run(m, m.words(*[push] * 11, END))
check("matrix stack overflow" in kinds(r), "too many matrix pushes are caught")

deep = m.words(END)
for _ in range(19):
    deep = m.words((dl.G_DL << 24, deep), END)
r = run(m, deep)
check("display lists nested past 18 levels" in kinds(r) and r["deepest"] == 19, "nesting past the limit is caught")
deep = m.words(END)
for _ in range(17):
    deep = m.words((dl.G_DL << 24, deep), END)
r = run(m, deep)
check(not r["problems"], "17 levels are allowed")

# LoadBlock of 16-bit texels: 2048 fit exactly, 2049 don't. lrs is the last texel.
settimg = (dl.G_SETTIMG << 24 | 2 << 19, 0x2000)
r = run(m, m.words(settimg, (dl.G_LOADBLOCK << 24, 2047 << 12), END))
check(not r["problems"] and r["largest_load"] == 4096, "a 4 KB LoadBlock is allowed")
r = run(m, m.words(settimg, (dl.G_LOADBLOCK << 24, 2048 << 12), END))
check("texture load past 4 KB of TMEM" in kinds(r), "a LoadBlock over 4 KB is caught")
# The same load starting halfway through TMEM.
settile = (dl.G_SETTILE << 24 | 2 << 19 | 256, 0)
r = run(m, m.words(settimg, settile, (dl.G_LOADBLOCK << 24, 1100 << 12), END))
check("texture load past 4 KB of TMEM" in kinds(r), "a load counts from its TMEM offset")
# LoadTile: 64x64 at 16 bits is 8 KB. Coordinates are 10.2.
r = run(m, m.words(settimg, (dl.G_LOADTILE << 24, 63 * 4 << 12 | 63 * 4), END))
check("texture load past 4 KB of TMEM" in kinds(r), "an oversized LoadTile is caught")
r = run(m, m.words(settimg, (dl.G_LOADTILE << 24, 31 * 4 << 12 | 31 * 4), END))
check(not r["problems"] and r["largest_load"] == 2048, "a 32x32 LoadTile is 2 KB")
r = run(m, m.words((dl.G_SETTIMG << 24 | 2 << 19, 0x900000), END))
check("texture address outside 8 MB" in kinds(r), "a texture above 8 MB is caught")

# A texture rectangle takes three commands, and the other two mustn't be read as commands.
rectangle = (dl.G_TEXRECT << 24 | (16 * 4) << 12 | 16 * 4, 0)
r = run(m, m.words(rectangle, (0x64 << 24, 0), (0x64 << 24, 0), END))
check(not r["problems"] and abs(r["pixels"] - 256) < 1, f"a texture rectangle consumes its halves: {r['pixels']:.0f}")

# 2D rectangles near the edge are reported, and whether the scissor cuts them.
scissor = (0xED << 24 | (8 * 4) << 12 | 8 * 4, (312 * 4) << 12 | 232 * 4)
def rect(ulx, uly, lrx, lry):
    return (dl.G_TEXRECT << 24 | (lrx * 4) << 12 | lry * 4, (ulx * 4) << 12 | uly * 4)
r = run(m, m.words(scissor, rect(300, 100, 314, 116), (0x64 << 24, 0), (0x64 << 24, 0), END))
check(len(r["edge_rects"]) == 1 and r["edge_rects"][0]["clipped"], f"a rectangle past the scissor is reported: {r['edge_rects']}")
r = run(m, m.words(scissor, rect(100, 100, 120, 116), (0x64 << 24, 0), (0x64 << 24, 0), END))
check(not r["edge_rects"], "a rectangle in the middle isn't")
r = run(m, m.words(rect(0, 0, 320, 240), (0x64 << 24, 0), (0x64 << 24, 0), END))
check(not r["edge_rects"], "a full-screen rectangle isn't")

# A list that loops forever stops rather than hanging.
loop_at = m.top
m.words((dl.G_DL << 24 | 1 << 16, loop_at), END)
r = run(m, loop_at)
check("list never ends" in kinds(r), "an endless list is caught")

print("DL CHECK TESTS PASS" if not failures else "DL CHECK TESTS FAIL")
sys.exit(1 if failures else 0)
