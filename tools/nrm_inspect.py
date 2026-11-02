#!/usr/bin/env python3
"""Phase 0 recon: reads the .nrm mods, their link maps, the game's symbols and the ROM, writes REPORT.md.

The symbol file format follows N64Recomp src/mod_symbols.cpp (parse_v1). The tool stops if a file
isn't consumed exactly, or if a link map doesn't match its binary.

The ROM is only read. REPORT.md holds public symbol names, addresses, sizes and counts, never game
code bytes or disassembly.

usage: nrm_inspect.py [--rom rom/quest64.us.z64] [--notes tools/report_notes.md] [--out REPORT.md]
"""

import argparse
import collections
import hashlib
import json
import re
import struct
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DC = ROOT / "vendor/Eltale-Reborn-DC-Port"
PC = ROOT / "vendor/Eltale-Reborn"
ROM_SHA1 = "91b96e938c6d91699057fad91d726ee5a23ce33a"
MOD_BASE = 0x81000000
HOOK_AT_RETURN = 1
VROM_IMPORT = 0xFFFFFFFE
VROM_EVENT = 0xFFFFFFFD
VROM_SELF = 0x80000000
RELOC_NAMES = {2: "R_MIPS_32", 4: "R_MIPS_26", 5: "R_MIPS_HI16", 6: "R_MIPS_LO16"}
MODS = ("quest64_modern_gameplay", "eltale_reborn")

# Link-map modules by the brief's categories. Anything else lands in "Unlisted".
CATEGORIES = [
    ("Story data", r"npc_dialogue|act\d.*|finale.*|placements|scripts|signs"),
    ("Script/event engine", r"script|world|dialogue|text|flags|save"),
    ("Progression/economy/battle", r"items|economy|battle|battle_menu|crits|bosses"),
    ("Models", r"custom_model|bart_model|hair_models|.*_models|room_geometry"),
    ("2D/UI/FX", r"title|attract_logo|credits|license_notice|jp_assets|jp_hud|menu_slide|battle_rings|hit_spark|fx|daylight"),
    ("Audio", r"ambience|music|music_fade"),
    ("Debug", r"dev"),
]

# F3DEX 1.x command bytes (the game's microcode family per the DC port's NOTES.md) and RDP commands.
F3DEX_OPS = {
    0x00: "SPNOOP", 0x01: "MTX", 0x03: "MOVEMEM", 0x04: "VTX", 0x06: "DL", 0xAF: "LOAD_UCODE", 0xB0: "BRANCH_Z",
    0xB1: "TRI2", 0xB2: "MODIFYVTX", 0xB3: "RDPHALF_2", 0xB4: "RDPHALF_1", 0xB5: "QUAD", 0xB6: "CLEARGEOMETRYMODE",
    0xB7: "SETGEOMETRYMODE", 0xB8: "ENDDL", 0xB9: "SETOTHERMODE_L", 0xBA: "SETOTHERMODE_H", 0xBB: "TEXTURE",
    0xBC: "MOVEWORD", 0xBD: "POPMTX", 0xBE: "CULLDL", 0xBF: "TRI1", 0xC0: "NOOP",
}
RDP_OPS = {
    0xE4: "TEXRECT", 0xE5: "TEXRECTFLIP", 0xE6: "RDPLOADSYNC", 0xE7: "RDPPIPESYNC", 0xE8: "RDPTILESYNC",
    0xE9: "RDPFULLSYNC", 0xEA: "SETKEYGB", 0xEB: "SETKEYR", 0xEC: "SETCONVERT", 0xED: "SETSCISSOR",
    0xEE: "SETPRIMDEPTH", 0xEF: "RDPSETOTHERMODE", 0xF0: "LOADTLUT", 0xF2: "SETTILESIZE", 0xF3: "LOADBLOCK",
    0xF4: "LOADTILE", 0xF5: "SETTILE", 0xF6: "FILLRECT", 0xF7: "SETFILLCOLOR", 0xF8: "SETFOGCOLOR",
    0xF9: "SETBLENDCOLOR", 0xFA: "SETPRIMCOLOR", 0xFB: "SETENVCOLOR", 0xFC: "SETCOMBINE", 0xFD: "SETTIMG",
    0xFE: "SETZIMG", 0xFF: "SETCIMG",
}
GBI_OPS = {**F3DEX_OPS, **RDP_OPS}
F3DEX2_ONLY = {0xD7: "TEXTURE", 0xD8: "POPMTX", 0xD9: "GEOMETRYMODE", 0xDA: "MTX", 0xDB: "MOVEWORD", 0xDC: "MOVEMEM",
               0xDD: "LOAD_UCODE", 0xDE: "DL", 0xDF: "ENDDL", 0xE0: "SPNOOP", 0xE1: "RDPHALF_1", 0xE2: "SETOTHERMODE_L",
               0xE3: "SETOTHERMODE_H"}
RT64_MAGIC = 0x00525464
RT64_EX_OP = 0x64
TMEM_SIZE = 4096

# Masks and sizes that would treat an address as "inside 4 MB" or similar.
MASK_LUIS = {0x003F, 0x0040, 0x007F, 0x0080, 0x00FF, 0x0100, 0x1FFF, 0x7FFF}
THREAD_ENTRY_NOTE = "static `jal` graph from each `osCreateThread` entry; calls through pointers aren't followed"
CACHE_FUNCS = ("osWritebackDCacheAll", "osWritebackDCache", "osInvalDCache", "osInvalICache")
TASK_FUNCS = ("osSpTaskLoad", "osSpTaskStartGo")
# The two floor probe functions, which NOTES.md says cost 16% of a battle on the DC port.
FLOOR_PROBE = ("func_8000F238", "func_8000F5A4")


def fail(msg):
    sys.exit(f"nrm_inspect: error: {msg}")


def w32(buf, off):
    return struct.unpack_from(">I", buf, off)[0]


def sign16(v):
    return (v & 0xFFFF) - 0x10000 if v & 0x8000 else v & 0xFFFF


def hx(v):
    return f"0x{v:X}"


# --- Game symbols and ROM ---

class Func:
    def __init__(self, name, vram, size, section):
        self.name, self.vram, self.size, self.section = name, vram, size, section

    @property
    def rom(self):
        return self.section["rom"] + self.vram - self.section["vram"]


def load_game_funcs():
    with open(PC / "Quest64Syms/dump.toml", "rb") as f:
        syms = tomllib.load(f)
    sections, by_key, by_name, by_vram = [], {}, {}, collections.defaultdict(list)
    for sec in syms["section"]:
        sections.append(sec)
        for fn in sec.get("functions", []):
            func = Func(fn["name"], fn["vram"], fn["size"], sec)
            by_key[(sec["rom"], fn["vram"])] = func
            by_name[fn["name"]] = func
            by_vram[fn["vram"]].append(func)
    return sections, by_key, by_name, by_vram


def control_flow(word):
    op, rt, fn = word >> 26, (word >> 16) & 31, word & 63
    if op in (2, 3):
        return "jump"
    if op in (4, 5, 6, 7, 20, 21, 22, 23) or (op == 1 and rt in (0, 1, 2, 3, 16, 17, 18, 19)):
        return "branch"
    if op == 0x11 and (word >> 21) & 31 == 8:
        return "branch"
    if op == 0 and fn in (8, 9):
        return "jr"
    return None


def is_pc_relative(word):
    return control_flow(word) == "branch"


class FuncScan:
    """What the hook engine needs to know about one game function."""

    def __init__(self, func, rom):
        words = [w32(rom, func.rom + i) for i in range(0, func.size, 4)]
        self.first_two = [control_flow(w) for w in words[:2]]
        self.jr_ra = sum(w == 0x03E00008 for w in words)
        self.jr_other = 0
        self.jr_table = 0
        self.tail_jumps = 0
        self.branch_into_head = 0
        self.has_frame = any((w >> 16) == 0x27BD and w & 0x8000 for w in words[:4])
        self.calls = sum((w >> 26) == 3 for w in words) + sum((w >> 26) == 0 and (w & 63) == 9 for w in words)
        for i, w in enumerate(words):
            kind = control_flow(w)
            if kind == "branch" and (i + 1 + sign16(w)) in (0, 1):
                self.branch_into_head += 1
            if kind == "jump" and (w >> 26) == 2:
                target = (w & 0x3FFFFFF) << 2 | 0x80000000
                if target in (func.vram, func.vram + 4):
                    self.branch_into_head += 1
                if not func.vram <= target < func.vram + func.size:
                    self.tail_jumps += 1
            if kind == "jr" and (w & 63) == 8 and w != 0x03E00008:
                # A jump table: the register came from a load just before the jr.
                reg = (w >> 21) & 31
                table = any((p >> 26) == 0x23 and (p >> 16) & 31 == reg for p in words[max(0, i - 4):i])
                if table:
                    self.jr_table += 1
                else:
                    self.jr_other += 1
        self.jal_targets = [(w & 0x3FFFFFF) << 2 | 0x80000000 for w in words if (w >> 26) == 3]


def game_call_graph(by_key, rom):
    return {key: FuncScan(func, rom) for key, func in by_key.items()}


def find_threads(by_key, by_vram, by_name, rom):
    """Finds each osCreateThread site and reads its id (a1), entry (a2) from the code around the call."""
    create = by_name["osCreateThread"].vram
    threads = []
    for func in by_key.values():
        words = [w32(rom, func.rom + i) for i in range(0, func.size, 4)]
        for i, w in enumerate(words):
            if (w >> 26) != 3 or ((w & 0x3FFFFFF) << 2 | 0x80000000) != create:
                continue
            regs = {}
            for p in words[max(0, i - 14):i + 2]:
                op, rs, rt, imm = p >> 26, (p >> 21) & 31, (p >> 16) & 31, p & 0xFFFF
                if p == 0:
                    continue
                if op == 15:
                    regs[rt] = imm << 16
                elif op == 9:
                    regs[rt] = ((regs.get(rs, 0) if rs else 0) + sign16(imm)) & 0xFFFFFFFF
                elif op == 13:
                    regs[rt] = (regs.get(rs, 0) if rs else 0) | imm
            threads.append((regs.get(6), regs.get(5), func.name))
    return threads


def reachable(entry, by_vram, scans):
    seen, todo = set(), [entry]
    while todo:
        vram = todo.pop()
        for func in by_vram.get(vram, []):
            key = (func.section["rom"], func.vram)
            if key in seen:
                continue
            seen.add(key)
            todo.extend(scans[key].jal_targets)
    return seen


# --- Mods ---

class Mod:
    pass


def parse_syms(name, data, binary):
    mod = Mod()
    mod.name, mod.bin = name, binary
    if data[:8] != b"N64RSYMS":
        fail(f"{name}: bad magic")
    version, nsec, ndep, nimp, ndev, nrep, nexp, ncb, nev, nhook, nstr = struct.unpack_from("<11I", data, 8)
    if version != 1:
        fail(f"{name}: symbol file version {version}")
    if nsec != 1:
        fail(f"{name}: expected one section, found {nsec}")
    off = 52
    strings = data[off:off + nstr]
    off = (off + nstr + 3) & ~3

    def text(start, size):
        return strings[start:start + size].decode()

    def take(fmt, count):
        nonlocal off
        size = struct.calcsize(fmt)
        items = [struct.unpack_from(fmt, data, off + i * size) for i in range(count)]
        off += count * size
        return items

    flags, file_offset, mod.vram, mod.size, mod.bss, nfunc, nreloc = take("<7I", 1)[0]
    if flags:
        fail(f"{name}: section flags {flags:#x} (fixed-address sections aren't supported)")
    if file_offset != 0 or mod.vram != MOD_BASE:
        fail(f"{name}: section at file offset {file_offset:#x}, vram {mod.vram:#x}")
    if mod.size != len(binary):
        fail(f"{name}: section size {mod.size:#x} but mod_binary.bin is {len(binary):#x}")
    mod.funcs = take("<2I", nfunc)
    mod.relocs = take("<4I", nreloc)
    mod.deps = [text(a, n) for _, a, n in take("<B3xII", ndep)]
    mod.imports = [(text(a, n), mod.deps[d]) for a, n, d in take("<3I", nimp)]
    mod.dep_events = take("<3I", ndev)
    mod.patches = take("<4I", nrep)
    mod.exports = [(i, text(a, n)) for i, a, n in take("<3I", nexp)]
    mod.callbacks = take("<2I", ncb)
    mod.events = [text(a, n) for a, n in take("<2I", nev)]
    mod.hooks = take("<4I", nhook)
    if off != len(data):
        fail(f"{name}: symbol file has {len(data) - off} bytes left over")
    return mod


class MapEntry:
    def __init__(self, vma, size, out, module, section):
        self.vma, self.size, self.out, self.module, self.section = vma, size, out, module, section
        self.symbols = []


def parse_map(path, mod):
    """lld map: output sections at indent 0, input sections at 8, symbols at 16."""
    line_re = re.compile(r"^\s*([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+(\d+) (\s*)(.*)$")
    outs, entries, out, cur = [], [], None, None
    for line in Path(path).read_text().splitlines():
        m = line_re.match(line)
        if not m:
            continue
        vma, size = int(m.group(1), 16), int(m.group(3), 16)
        indent, rest = len(m.group(5)), m.group(6)
        # Symbol tables and debug info aren't loaded; they sit at address 0.
        if vma == 0:
            continue
        if indent == 0:
            if "RAMBASE" in rest:
                continue
            out = rest
            outs.append((vma, size, rest))
        elif indent == 8:
            mm = re.search(r"([^\\/:]+)\.o:\((.+)\)$", rest)
            if mm:
                module, section = mm.group(1), mm.group(2)
            else:
                mm = re.search(r"<internal>:\((.+)\)$", rest)
                module, section = "<merged>", mm.group(1) if mm else rest
            cur = MapEntry(vma, size, out, module, section)
            entries.append(cur)
        elif indent == 16 and cur is not None:
            cur.symbols.append((vma, size, rest))
    entries.sort(key=lambda e: e.vma)
    mod.map_outs, mod.map_entries = outs, entries
    mod.map_starts = [e.vma for e in entries]
    end = max(v + s for v, s, _ in outs)
    want = mod.vram + mod.size + mod.bss
    if end != want:
        fail(f"{mod.name}: link map ends at {end:#x}, symbols say {want:#x}")
    return mod


def locate(mod, vma):
    """Returns (module, symbol name) for an address in the mod."""
    import bisect
    i = bisect.bisect_right(mod.map_starts, vma) - 1
    while i >= 0 and mod.map_entries[i].size == 0:
        i -= 1
    if i < 0:
        return "?", hx(vma)
    e = mod.map_entries[i]
    if not e.vma <= vma < e.vma + e.size:
        return "?", hx(vma)
    sym = next((s for s in e.symbols if s[0] <= vma < s[0] + max(s[1], 1)), None)
    return e.module, sym[2] if sym else e.section


def category_of(module):
    for cat, pat in CATEGORIES:
        if re.fullmatch(pat, module):
            return cat
    return "Unlisted"


def code_words(mod):
    for start, size in mod.funcs:
        for off in range(start, start + size, 4):
            yield off, w32(mod.bin, off)


def code_offsets(mod):
    return {off for off, _ in code_words(mod)}


def size_classes(mod):
    classes = collections.Counter()
    for _, size, name in mod.map_outs:
        if name.startswith(".rodata"):
            classes["rodata"] += size
        elif name.startswith(".recomp_import"):
            classes["import stubs"] += size
        elif name.startswith((".text", ".recomp_hook", ".recomp_patch")):
            classes["code"] += size
        elif name.startswith(".data"):
            classes["data"] += size
        elif name.startswith(".bss"):
            classes["bss"] += size
        else:
            classes["other"] += size
    return classes


def module_sizes(mod):
    sizes = collections.defaultdict(collections.Counter)
    for e in mod.map_entries:
        if e.section.startswith(".recomp_import"):
            continue
        kind = ("rodata" if e.section.startswith(".rodata") else
                "bss" if e.section.startswith(".bss") else
                "data" if e.section.startswith(".data") else "code")
        sizes[e.module][kind] += e.size
    return sizes


def unrelocated_constants(mod):
    """lui of an address-like or mask-like value that no relocation covers."""
    hi = {r[0] for r in mod.relocs if r[1] == 5}
    addr, masks = [], []
    for off, w in code_words(mod):
        if (w >> 26) != 15 or off in hi:
            continue
        imm = w & 0xFFFF
        if 0x8040 <= imm <= 0x81FF:
            addr.append((off, imm))
        elif imm in MASK_LUIS:
            masks.append((off, imm))
    return addr, masks


def describe_constant(mod, off):
    """The full value of a lui + optional ori/addiu, and the instructions that use it."""
    w = w32(mod.bin, off)
    rt = (w >> 16) & 31
    value = (w & 0xFFFF) << 16
    use = []
    for i in range(1, 6):
        p = w32(mod.bin, off + 4 * i)
        op, rs, prt, fn = p >> 26, (p >> 21) & 31, (p >> 16) & 31, p & 63
        if op == 13 and rs == rt and prt == rt:
            value |= p & 0xFFFF
        elif op == 9 and rs == rt and prt == rt:
            value = (value + sign16(p)) & 0xFFFFFFFF
        elif op == 0 and fn in (0x2A, 0x2B) and rt in (rs, prt):
            use.append("slt" if fn == 0x2A else "sltu")
        elif op == 0 and fn == 0x24 and rt in (rs, prt):
            use.append("and")
        elif op in (4, 5) and rt in (rs, prt):
            use.append("beq" if op == 4 else "bne")
        elif op == 0x2B and prt == rt:
            use.append("sw")
    return value, use


def float_to_int_sites(mod):
    sites = collections.Counter()
    for off, w in code_words(mod):
        if (w >> 26) == 0x11:
            fmt, fn = (w >> 21) & 31, w & 63
            if fmt in (16, 17) and fn in (0x0C, 0x0D, 0x0E, 0x0F, 0x24, 0x25, 0x09, 0x08, 0x0A, 0x0B):
                sites[locate(mod, mod.vram + off)] += 1
    return sites


def fp_alignment_counts(mod):
    c = collections.Counter()
    for _, w in code_words(mod):
        op = w >> 26
        if op in (0x35, 0x3D):
            c["ldc1/sdc1"] += 1
        elif op in (0x37, 0x3F):
            c["ld/sd"] += 1
        elif op in (0x22, 0x26, 0x2A, 0x2E):
            c["lwl/lwr/swl/swr"] += 1
        elif op == 0x1C:
            c["SPECIAL2 (MIPS32)"] += 1
        elif op == 0 and w & 63 in (0x0A, 0x0B):
            c["movz/movn (MIPS32)"] += 1
        elif op == 0 and w & 63 == 0x34:
            c["teq"] += 1
        elif op == 0 and w & 63 == 0x0D:
            c["break"] += 1
    return c


def stack_arg_hooks(mod):
    """Hook functions that read above their own frame: incoming stack arguments."""
    found = {}
    entries = [h[0] for h in mod.hooks] + [r[0] for r in mod.patches]
    for index in set(entries):
        start, size = mod.funcs[index]
        # The prologue can sit after early guards, so the frame applies from where it's first seen.
        frame = 0
        reads = []
        for off in range(start, start + size, 4):
            w = w32(mod.bin, off)
            op, rs, imm = w >> 26, (w >> 21) & 31, sign16(w)
            if (w >> 16) == 0x27BD and w & 0x8000 and not frame:
                frame = -imm
                continue
            if rs == 29 and op in (0x20, 0x21, 0x23, 0x24, 0x25, 0x31, 0x35) and imm >= frame + 16:
                reads.append(imm - frame)
        if reads:
            found[index] = sorted(set(reads))
    return found


def gbi_code_scan(mod):
    """lui immediates that look like GBI word 0, kept if the value is stored or passed as an argument."""
    sites = collections.defaultdict(collections.Counter)
    weak = 0
    words = dict(code_words(mod))
    for off, w in words.items():
        if (w >> 26) != 15:
            continue
        op_byte = (w >> 8) & 0xFF
        imm = w & 0xFFFF
        if op_byte not in GBI_OPS and op_byte not in F3DEX2_ONLY and op_byte != RT64_EX_OP:
            continue
        if imm == 0xFFFF or op_byte < 0x10:
            continue
        rt = (w >> 16) & 31
        verdict = None
        for i in range(1, 9):
            p = words.get(off + 4 * i)
            if p is None:
                break
            pop, prs, prt = p >> 26, (p >> 21) & 31, (p >> 16) & 31
            if pop == 0x11 and prs == 4 and prt == rt:
                verdict = "float"
                break
            if pop == 0x2B and prt == rt:
                verdict = "emit"
                break
            if pop == 3 and rt in (5, 6, 7):
                verdict = "emit"
                break
            if pop == 15 and prt == rt:
                break
        if verdict == "emit":
            sites[locate(mod, mod.vram + off)][op_byte] += 1
        elif verdict is None:
            weak += 1
    return sites, weak


def rt64_sites(mod):
    """Every place code writes the RT64 enable magic or an extended command."""
    words = dict(code_words(mod))
    magic, extended = collections.Counter(), collections.defaultdict(list)
    for off, w in words.items():
        if (w >> 26) != 15:
            continue
        imm = w & 0xFFFF
        rt = (w >> 16) & 31
        if imm == RT64_MAGIC >> 16:
            # The ori can be further along, and can write a different register.
            for i in range(1, 12):
                nxt = words.get(off + 4 * i, 0)
                if (nxt >> 26) == 13 and (nxt >> 21) & 31 == rt and nxt & 0xFFFF == RT64_MAGIC & 0xFFFF:
                    magic[locate(mod, mod.vram + off)] += 1
                    break
        if imm == RT64_EX_OP << 8:
            low = 0
            for i in range(1, 24):
                nxt = words.get(off + 4 * i, 0)
                if (nxt >> 26) == 13 and (nxt >> 21) & 31 == rt:
                    low = nxt & 0xFFFF
                    break
                if (nxt >> 26) == 15 and (nxt >> 16) & 31 == rt:
                    break
            extended[locate(mod, mod.vram + off)].append(low)
    data_magic = [off for off in range(0, len(mod.bin) & ~3, 4) if off not in words and w32(mod.bin, off) == RT64_MAGIC]
    # Merged strings are left out: text can hold these bytes by chance.
    data_extended = [off for off in range(0, len(mod.bin) & ~3, 4)
                     if off not in words and w32(mod.bin, off) >> 8 == RT64_EX_OP << 16
                     and locate(mod, mod.vram + off)[0] != "<merged>"]
    return magic, extended, data_magic, data_extended


def static_display_lists(mod):
    """Runs of valid commands in data that end with G_ENDDL, walked backward from the terminator."""
    code = code_offsets(mod)
    lists = []
    # Gfx arrays in these mods can be only 4-byte aligned.
    for end in range(0, (len(mod.bin) - 8) & ~3, 4):
        if end in code or w32(mod.bin, end) != 0xB8000000 or w32(mod.bin, end + 4) != 0:
            continue
        start = end
        # Stop at the previous list's end, and at zero padding, which also decodes as SPNOOP.
        while start >= 8 and (start - 8) not in code and w32(mod.bin, start - 8) >> 24 in (*GBI_OPS, RT64_EX_OP) \
                and w32(mod.bin, start - 8) != 0xB8000000 and w32(mod.bin, start - 8) != 0:
            start -= 8
        ops = collections.Counter(w32(mod.bin, o) >> 24 for o in range(start, end + 8, 8))
        lists.append((start, end + 8 - start, ops))
    foreign = 0
    for start, size, _ in lists:
        for o in range(start, start + size, 8):
            b = w32(mod.bin, o) >> 24
            if b == RT64_EX_OP or b in F3DEX2_ONLY:
                foreign += 1
    return lists, foreign


def tile_load_sites(mod):
    """Texture-load commands in code, with constant sizes where the code spells them out."""
    words = dict(code_words(mod))
    out = []
    for off, w in sorted(words.items()):
        if (w >> 26) != 15 or (w >> 8) & 0xFF not in (0xF2, 0xF3, 0xF4):
            continue
        op = (w >> 8) & 0xFF
        rt = (w >> 16) & 31
        word1 = None
        for i in range(1, 16):
            p = words.get(off + 4 * i)
            if p is None:
                break
            if (p >> 26) == 15 and (p >> 16) & 31 != rt and (p & 0xFFFF) >> 8 < 8:
                reg = (p >> 16) & 31
                value = (p & 0xFFFF) << 16
                for j in range(i + 1, i + 12):
                    q = words.get(off + 4 * j, 0)
                    if (q >> 26) == 13 and (q >> 21) & 31 == reg and (q >> 16) & 31 == reg:
                        value |= q & 0xFFFF
                        break
                word1 = value
                break
        out.append((locate(mod, mod.vram + off), op, word1))
    return out


def large_images(mod):
    """Read-only symbols over the TMEM size, from modules that draw images."""
    out = []
    for e in mod.map_entries:
        if not e.section.startswith(".rodata"):
            continue
        for vma, size, name in e.symbols:
            if size > TMEM_SIZE and category_of(e.module) in ("2D/UI/FX", "Models", "Unlisted"):
                out.append((e.module, name, size))
    return sorted(out, key=lambda x: -x[2])


# --- Report ---

def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def git_rev(path):
    return subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()


def target_name(by_key, rom_addr, vram):
    func = by_key.get((rom_addr, vram))
    return func


def report_mod(mod, by_key, scans, hot, thread_reach, out):
    a = out.append
    display = mod.name
    a(f"\n## {display}\n")

    a("### Image size\n")
    classes = size_classes(mod)
    rows = [(k, hx(v), f"{v / 1024:.1f} KB") for k, v in classes.most_common()]
    rows.append(("**total**", hx(mod.size + mod.bss), f"{(mod.size + mod.bss) / 1024:.1f} KB"))
    a(md_table(["Class", "Bytes", "Size"], rows))
    a(f"\nFunctions in the symbol file: {len(mod.funcs)}, {sum(s for _, s in mod.funcs) / 1024:.1f} KB of code.\n")

    a("### Imports and relocations\n")
    a(md_table(["Import", "From"], [(f"`{n}`", f"`{d}`") for n, d in mod.imports]))
    counts = collections.Counter(r[1] for r in mod.relocs)
    def target_kind(r):
        if r[3] == VROM_IMPORT:
            return "import"
        if r[3] == VROM_EVENT:
            return "event"
        return "self" if r[3] & VROM_SELF else "game"
    by_kind = collections.Counter((RELOC_NAMES.get(r[1], r[1]), target_kind(r)) for r in mod.relocs)
    a("")
    a(md_table(["Type", "Count", "Targets"],
               [(RELOC_NAMES.get(t, t), n, ", ".join(f"{k}: {v}" for (tt, k), v in sorted(by_kind.items()) if tt == RELOC_NAMES.get(t, t)))
                for t, n in sorted(counts.items())]))
    a(f"\nExports: {len(mod.exports)}. Events: {len(mod.events)}. Callbacks: {len(mod.callbacks)}. "
      f"Dependencies: {', '.join('`' + d + '`' for d in mod.deps)}.\n")

    a("### Patches and hooks\n")
    rows = []
    records = [("PATCH", r) for r in mod.patches]
    records += [("HOOK_RETURN" if h[3] & HOOK_AT_RETURN else "HOOK", h) for h in mod.hooks]
    per_category = collections.defaultdict(collections.Counter)
    per_module = collections.defaultdict(collections.Counter)
    for kind, r in sorted(records, key=lambda x: (x[1][2], x[0])):
        func = by_key.get((r[1], r[2]))
        if func is None:
            fail(f"{mod.name}: {kind} target {r[2]:#x} in section {r[1]:#x} isn't in dump.toml")
        scan = scans[(r[1], r[2])]
        start = mod.funcs[r[0]][0]
        module, symbol = locate(mod, mod.vram + start)
        per_category[category_of(module)][kind] += 1
        per_module[module][kind] += 1
        flags = []
        if func.size < 8:
            flags.append("under 8 bytes")
        if func.size < 16 and kind == "HOOK":
            flags.append("short")
        if kind == "HOOK":
            if any(scan.first_two):
                flags.append("control flow in first 2: " + "/".join(str(x) for x in scan.first_two))
            if scan.branch_into_head:
                flags.append("branch into first 2")
        if kind == "HOOK_RETURN":
            if scan.jr_ra == 0:
                flags.append("no jr ra")
            if scan.tail_jumps:
                flags.append(f"{scan.tail_jumps} tail jumps")
            if scan.jr_other:
                flags.append(f"{scan.jr_other} unclassified jr")
            if scan.jr_table:
                flags.append(f"{scan.jr_table} jump table")
        if not scan.has_frame:
            flags.append("leaf, no frame")
        if func.name in hot:
            flags.append("DC hot list")
        if func.name in FLOOR_PROBE:
            flags.append("floor probe")
        threads = thread_reach.get((r[1], r[2]), [])
        rows.append((kind, f"`{func.name}`", hx(func.vram), hx(func.size), func.section["name"],
                     scan.jr_ra if kind == "HOOK_RETURN" else "", ",".join(threads) if threads else "indirect only",
                     f"{module}", "; ".join(flags)))
    a(md_table(["Type", "Target", "VRAM", "Size", "Section", "`jr ra`", "Thread (static)", "Mod module", "Flags"], rows))

    a("\n### Records by module\n")
    a(md_table(["Module", "Category", "Patches", "Entry hooks", "Return hooks"],
               [(m, category_of(m), c["PATCH"], c["HOOK"], c["HOOK_RETURN"]) for m, c in sorted(per_module.items())]))

    a("\n### Sizes by module and category\n")
    sizes = module_sizes(mod)
    cats = collections.defaultdict(collections.Counter)
    for module, c in sizes.items():
        cats["(merged strings)" if module == "<merged>" else category_of(module)].update(c)
    a(md_table(["Category", "Code", "Read-only", "Data", "Bss", "Patches", "Entry", "Return"],
               [(cat, f"{c['code'] / 1024:.1f} KB", f"{c['rodata'] / 1024:.1f} KB", f"{c['data'] / 1024:.1f} KB", f"{c['bss'] / 1024:.1f} KB",
                 per_category[cat]["PATCH"], per_category[cat]["HOOK"], per_category[cat]["HOOK_RETURN"])
                for cat, c in sorted(cats.items())]))
    unlisted = sorted(m for m in sizes if category_of(m) == "Unlisted" and m != "<merged>")
    if unlisted:
        a(f"\nModules not in the brief's table: {', '.join('`' + m + '`' for m in unlisted)}.")

    a("\n### Constants the relocations don't cover\n")
    addr, masks = unrelocated_constants(mod)
    if addr:
        rows = []
        for off, imm in addr:
            value, use = describe_constant(mod, off)
            module, sym = locate(mod, mod.vram + off)
            rows.append((hx(off), hx(value), f"`{sym}`", module, ", ".join(use) or "-"))
        a(md_table(["Binary offset", "Value", "Function", "Module", "Used by"], rows))
    else:
        a("No unrelocated `lui` in 0x8040-0x81FF.")
    if masks:
        a("\nMask-like or size-like `lui` values (mostly harmless; review the ones used with `and` or a compare):\n")
        rows = []
        for off, imm in masks:
            value, use = describe_constant(mod, off)
            if not set(use) & {"and", "slt", "sltu"}:
                continue
            module, sym = locate(mod, mod.vram + off)
            rows.append((hx(off), hx(value), f"`{sym}`", module, ", ".join(use)))
        a(md_table(["Binary offset", "Value", "Function", "Module", "Used by"], rows) if rows else "None used with `and` or a compare.")
    code = code_offsets(mod)
    r32 = {r[0] for r in mod.relocs if r[1] == 2}
    end = mod.vram + mod.size + mod.bss
    stray = [off for off in range(0, len(mod.bin) & ~3, 4)
             if off not in code and off not in r32 and mod.vram <= w32(mod.bin, off) < end and w32(mod.bin, off) & 3 == 0]
    a(f"\nData words that look like pointers into the image with no relocation: {len(stray)}.")
    if stray:
        a(md_table(["Binary offset", "Value", "Symbol"], [(hx(o), hx(w32(mod.bin, o)), locate(mod, mod.vram + o)[1]) for o in stray[:30]]))

    a("\n### CPU checks\n")
    c = fp_alignment_counts(mod)
    a(md_table(["Instruction group", "Count"], [(k, c[k]) for k in sorted(c)] or [("none of note", 0)]))
    sites = float_to_int_sites(mod)
    a(f"\nFloat-to-int conversions: {sum(sites.values())} sites. They raise an exception on real hardware for NaN or out-of-range input.\n")
    if sites:
        by_mod = collections.Counter()
        for (module, _), n in sites.items():
            by_mod[module] += n
        a(md_table(["Module", "Sites"], by_mod.most_common()))

    a("\n### Stack arguments\n")
    stack = stack_arg_hooks(mod)
    if stack:
        rows = []
        for index, reads in sorted(stack.items()):
            module, sym = locate(mod, mod.vram + mod.funcs[index][0])
            rows.append((f"`{sym}`", module, ", ".join(hx(r) for r in reads)))
        a(md_table(["Hook or patch", "Module", "Offsets above its frame"], rows))
    else:
        a("No hook or patch reads incoming stack arguments.")

    a("\n### GBI in code\n")
    gbi, weak = gbi_code_scan(mod)
    rows = []
    for (module, sym), ops in sorted(gbi.items()):
        rows.append((module, f"`{sym}`", ", ".join(f"{GBI_OPS.get(b) or F3DEX2_ONLY.get(b) or hex(b)}×{n}" for b, n in sorted(ops.items()))))
    a(md_table(["Module", "Function", "Commands written"], rows) if rows else "No commands found in code.")
    a(f"\n{weak} other `lui` values share a GBI command byte but were never seen stored or passed, so they're left out. "
      "Words loaded from tables or passed further than the next call aren't seen by this scan.\n")
    a("### RT64 and foreign commands\n")
    magic, extended, data_magic, data_extended = rt64_sites(mod)
    rows = [(m, f"`{s}`", "enable magic", n) for (m, s), n in sorted(magic.items())]
    rows += [(m, f"`{s}`", "extended command " + ", ".join(hx(v) for v in sorted(vals)), len(vals)) for (m, s), vals in sorted(extended.items())]
    a(md_table(["Module", "Function", "Writes", "Sites"], rows) if rows else "None in code.")
    a(f"\nIn data: RT64 enable magic {len(data_magic)} places, extended commands {len(data_extended)} places.")
    if data_extended:
        a("")
        a(md_table(["Binary offset", "Word", "Module"], [(hx(o), f"{w32(mod.bin, o):#010x}", locate(mod, mod.vram + o)[0]) for o in data_extended]))
    foreign_code = [(key, b, n) for key, ops in gbi.items() for b, n in ops.items() if b in F3DEX2_ONLY]
    if foreign_code:
        a(md_table(["Function", "F3DEX2-only byte", "Count"], [(f"`{k[1]}`", hex(b), n) for k, b, n in foreign_code]))
    lists, foreign = static_display_lists(mod)
    a(f"\nStatic display lists in data: {len(lists)}, {sum(s for _, s, _ in lists)} bytes. Foreign commands inside them: {foreign}.\n")
    if lists:
        by_module = collections.Counter()
        for start, size, _ in lists:
            by_module[locate(mod, mod.vram + start)[0]] += size
        a(md_table(["Module", "Bytes of static display lists"], by_module.most_common()))

    a("\n### Texture loads\n")
    loads = tile_load_sites(mod)
    rows = []
    for (module, sym), op, word1 in loads:
        detail = "size from registers"
        if word1 is not None:
            detail = f"constant, tile {word1 >> 24}, lrs {(word1 >> 12) & 0xFFF:#x}, {'dxt' if op == 0xF3 else 'lrt'} {word1 & 0xFFF:#x}"
        rows.append((module, f"`{sym}`", RDP_OPS[op], detail))
    a(md_table(["Module", "Function", "Command", "Size"], rows) if rows else "No texture loads in code.")
    images = large_images(mod)
    a(f"\nRead-only symbols over {TMEM_SIZE} bytes that may be images (candidates, to be confirmed in ares): {len(images)}.\n")
    if images:
        a(md_table(["Module", "Symbol", "Bytes"], [(m, f"`{s}`", size) for m, s, size in images[:40]]))
    a("")


def report_cross(mods, by_key, by_name, rom, out):
    a = out.append
    a("\n## Conflicts between the mods\n")
    gp, el = mods
    def keys(records):
        return {(r[1], r[2]) for r in records}
    shared = keys(gp.hooks) & keys(el.hooks)
    a(f"Functions hooked by both mods: {len(shared)}.\n")
    rows = []
    for key in sorted(shared, key=lambda k: k[1]):
        def kinds(m):
            ks = [("return" if h[3] & HOOK_AT_RETURN else "entry") for h in m.hooks if (h[1], h[2]) == key]
            return ", ".join(sorted(ks))
        rows.append((f"`{by_key[key].name}`", kinds(gp), kinds(el)))
    a(md_table(["Function", "Gameplay", "Eltale"], rows))
    patch_hook = (keys(gp.patches) & keys(el.hooks)) | (keys(el.patches) & keys(gp.hooks)) | (keys(el.patches) & keys(el.hooks)) | (keys(gp.patches) & keys(gp.hooks))
    a(f"\nFunctions both patched and hooked, in either mod: {', '.join('`' + by_key[k].name + '`' for k in sorted(patch_hook)) or 'none'}.")
    a(f"\nFunctions patched by both mods: {', '.join('`' + by_key[k].name + '`' for k in sorted(keys(gp.patches) & keys(el.patches))) or 'none'}.\n")


def report_game(by_name, by_key, rom, scans, threads, out):
    a = out.append
    a("\n## Game side\n")
    a("### Threads\n")
    a(f"From a {THREAD_ENTRY_NOTE}.\n")
    rows = []
    for entry, tid, creator in threads:
        names = [f.name for f in by_key.values() if f.vram == entry] if entry else []
        rows.append((tid if tid is not None else "?", hx(entry) if entry else "?", ", ".join(names) or "?", f"`{creator}`"))
    a(md_table(["Id", "Entry", "Name", "Created in"], rows))
    a("\n### Cache and RSP calls\n")
    rows = []
    for name in CACHE_FUNCS + TASK_FUNCS:
        func = by_name.get(name)
        if func is None:
            rows.append((f"`{name}`", "not in dump.toml", ""))
            continue
        callers = sorted(by_key[k].name for k, s in scans.items() if func.vram in s.jal_targets)
        rows.append((f"`{name}`", len(callers), ", ".join(f"`{c}`" for c in callers[:12])))
    a(md_table(["Function", "Callers", "Names"], rows))
    a("")


def report_game_calls(mods, by_key, by_name, out):
    a = out.append
    a("\n## Game functions the mods call\n")
    names = {}
    for f in by_key.values():
        names[(f.section["rom"], f.vram - f.section["vram"])] = f.name
    cache_vrams = {by_name[n].vram: n for n in CACHE_FUNCS + TASK_FUNCS + ("osPiStartDma",) if n in by_name}
    for mod in mods:
        counts = collections.Counter()
        for off, kind, target, vrom in mod.relocs:
            if kind == 4 and not vrom & VROM_SELF and vrom not in (VROM_IMPORT, VROM_EVENT):
                counts[names.get((vrom, target), f"{vrom:#x}+{target:#x}")] += 1
        a(f"**{mod.name}**: {sum(counts.values())} calls to {len(counts)} functions. "
          f"libultra cache, DMA or RSP calls among them: {', '.join(n for n in counts if n in cache_vrams.values()) or 'none'}.\n")


def report_config(mods_json, out):
    a = out.append
    a("\n## Config defaults\n")
    a("These become compile-time constants. The review of which to override is in the assessment.\n")
    rows = []
    for name, doc in mods_json:
        for o in doc["config_schema"]["options"]:
            rows.append((name, f"`{o['id']}`", o["type"], o["default"]))
    a(md_table(["Mod", "Option", "Type", "Default"], rows))
    a("")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", default=str(ROOT / "rom/quest64.us.z64"))
    ap.add_argument("--notes", default=str(ROOT / "tools/report_notes.md"))
    ap.add_argument("--out", default=str(ROOT / "REPORT.md"))
    args = ap.parse_args()

    rom = Path(args.rom).read_bytes()
    if hashlib.sha1(rom).hexdigest() != ROM_SHA1:
        fail(f"{args.rom} isn't the US Quest 64 ROM (SHA-1 {ROM_SHA1})")

    sections, by_key, by_name, by_vram = load_game_funcs()
    scans = game_call_graph(by_key, rom)
    threads = find_threads(by_key, by_vram, by_name, rom)
    thread_reach = collections.defaultdict(list)
    for entry, tid, _ in threads:
        if entry is None:
            continue
        for key in reachable(entry, by_vram, scans):
            thread_reach[key].append(str(tid))
    hot_path = DC / "runtime/hot.txt"
    hot = {line.strip() for line in hot_path.read_text().splitlines() if line.strip() and not line.startswith("#")}

    mods, docs, provenance = [], [], []
    for name in MODS:
        dc_nrm = DC / "eltale" / f"{name}.nrm"
        pc_nrm = PC / "mods" / f"{name}.nrm"
        sha = hashlib.sha1(dc_nrm.read_bytes()).hexdigest()
        if sha != hashlib.sha1(pc_nrm.read_bytes()).hexdigest():
            fail(f"{name}: the DC port's .nrm differs from the PC repo's, so the link map may not match")
        with zipfile.ZipFile(dc_nrm) as z:
            mod = parse_syms(name, z.read("mod_syms.bin"), z.read("mod_binary.bin"))
            docs.append((name, json.loads(z.read("mod.json"))))
        parse_map(DC / "eltale" / f"{name}.map", mod)
        mods.append(mod)
        provenance.append((name, sha, docs[-1][1]["version"]))

    out = ["# Phase 0 report", "",
           "Generated by `tools/nrm_inspect.py`. The assessment comes from `tools/report_notes.md`; everything after it is generated.", "",
           f"Sources: Eltale-Reborn `{git_rev(PC)}`, Eltale-Reborn-DC-Port `{git_rev(DC)}`, Quest64Syms `{git_rev(PC / 'Quest64Syms')}`. ROM SHA-1 `{ROM_SHA1}`.", ""]
    out.append(md_table(["Mod", "Version", ".nrm SHA-1 (same in both repos)"], [(n, v, f"`{s}`") for n, s, v in provenance]))
    notes = Path(args.notes)
    if notes.exists():
        out += ["", notes.read_text().rstrip()]
    report_cross(mods, by_key, by_name, rom, out)
    report_game(by_name, by_key, rom, scans, threads, out)
    report_game_calls(mods, by_key, by_name, out)
    report_config(docs, out)
    for mod in mods:
        report_mod(mod, by_key, scans, hot, thread_reach, out)

    Path(args.out).write_text("\n".join(out) + "\n")

    for mod in mods:
        entry = sum(not h[3] & HOOK_AT_RETURN for h in mod.hooks)
        print(f"{mod.name}: image {mod.size:#x} bss {mod.bss:#x} funcs {len(mod.funcs)} relocs {len(mod.relocs)} "
              f"patches {len(mod.patches)} hooks {entry}+{len(mod.hooks) - entry} exports {len(mod.exports)}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
