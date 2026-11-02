#!/usr/bin/env python3
"""Links mods into one image for 0x80400000 and works out the ROM patches that call into it.

Writes, in the output directory:
- image.bin: mods, runtime and trampolines, bss included, ready for the loader to DMA
- patches.json: the ROM words to change
- layout.json: where everything went

Entry hooks run in mod order, then any patch, then return hooks in reverse order, as the PC runtime does.
Mods are placed in memory in the order given, which is separate from hook_order.

usage: link_mods.py --out <dir> --mod <.nrm or dir>... [--hook-order id,id] [--set mod.key=value]...
"""

import argparse
import json
import os
import re
import struct
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import nrm_inspect as ni

ROOT = Path(__file__).resolve().parent.parent
IMAGE_BASE = 0x80400000
IMAGE_LIMIT = 0x807FFFF0
RUNNING_THREAD = 0x80070A00
THREAD_ID_OFFSET = 0x14
HOOK_FRAME_SLOTS = 32
ORIGINAL_BASE = 0x81000000
# Off: surfaces keep the original flicker, as on the Dreamcast port. The PC's smoothed alpha needs RT64.
SMOOTH_TRANSPARENCY = 0

CFLAGS = ["-target", "mips", "-mips2", "-mabi=32", "-O2", "-G0", "-mno-abicalls", "-mno-odd-spreg",
          "-mno-check-zero-division", "-fno-pic", "-ffreestanding", "-fno-builtin", "-fomit-frame-pointer",
          "-fno-stack-protector", "-ffunction-sections", "-Wall", "-Wextra", "-Werror"]

# Runtime functions that take the calling mod's index in the argument after the mod's own.
PER_MOD_IMPORTS = {"recomp_get_config_u32": "rt_config_u32", "recomp_get_config_double": "rt_config_double"}
PLAIN_IMPORTS = {
    "recomp_printf": "rt_printf",
    "recomphook_get_return_s32": "rt_get_return_s32",
    "recomphook_get_return_u16": "rt_get_return_u16",
    "recomp_is_dependency_met": "rt_is_dependency_met",
    "recomp_get_smooth_transparency": "rt_smooth_transparency",
}
NATIVE_DEPENDENCY = "."

# Everything that runs before the image is loaded: boot, the loader's own calls and the PI manager's thread.
BOOT_ROOTS = ("recomp_entrypoint", "func_80000450", "osCreatePiManager", "__osDevMgrMain", "osCreateMesgQueue",
              "osInvalDCache", "osInvalICache", "osWritebackDCache", "osPiStartDma", "osRecvMesg", "osSetIntMask")

# MIPS registers and the frame every trampoline uses. FRAME_V0 and FRAME_V1 are also in runtime/modrt.c.
AT, V0, V1, A0, A1, A2, A3, T0, T1, T2, SP, RA = 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 29, 31
FRAME_SIZE = 0x60
FRAME_ARGS = 0x10
FRAME_RA = 0x20
FRAME_V0 = 0x28
FRAME_V1 = 0x2C
FRAME_F12 = 0x30
FRAME_F14 = 0x38
FRAME_F0 = 0x40
FRAME_F2 = 0x48
FRAME_SLOT = 0x50
FRAME_SLOT_OLD = 0x54
NOP = 0
JR_RA = 0x03E00008


def fail(msg):
    sys.exit(f"link_mods: error: {msg}")


# --- Instruction encoding ---

def i_type(op, rs, rt, imm):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def addiu(rt, rs, imm): return i_type(9, rs, rt, imm)
def andi(rt, rs, imm): return i_type(12, rs, rt, imm)
def lui(rt, imm): return i_type(15, 0, rt, imm)
def lw(rt, base, off): return i_type(0x23, base, rt, off)
def sw(rt, base, off): return i_type(0x2B, base, rt, off)
def ldc1(ft, base, off): return i_type(0x35, base, ft, off)
def sdc1(ft, base, off): return i_type(0x3D, base, ft, off)
def addu(rd, rs, rt): return (rs << 21) | (rt << 16) | (rd << 11) | 0x21
def sll(rd, rt, sa): return (rt << 16) | (rd << 11) | (sa << 6)
def j(target): return (2 << 26) | ((target & 0x0FFFFFFF) >> 2)
def jal(target): return (3 << 26) | ((target & 0x0FFFFFFF) >> 2)


def hi(addr):
    return ((addr + 0x8000) >> 16) & 0xFFFF


def lo(addr):
    return addr & 0xFFFF


def save_args():
    return [sw(A0 + i, SP, FRAME_ARGS + 4 * i) for i in range(4)]


def restore_args():
    return [lw(A0 + i, SP, FRAME_ARGS + 4 * i) for i in range(4)]


def open_frame():
    return [addiu(SP, SP, -FRAME_SIZE), sw(RA, SP, FRAME_RA)] + save_args()


def close_frame():
    return [lw(RA, SP, FRAME_RA), addiu(SP, SP, FRAME_SIZE)]


def save_results():
    return [sw(V0, SP, FRAME_V0), sw(V1, SP, FRAME_V1), sdc1(0, SP, FRAME_F0), sdc1(2, SP, FRAME_F2)]


def restore_results():
    return [lw(V0, SP, FRAME_V0), lw(V1, SP, FRAME_V1), ldc1(0, SP, FRAME_F0), ldc1(2, SP, FRAME_F2)]


def enter_slot(frames):
    """Publishes this frame for recomphook_get_return_*, per thread and keeping the previous value."""
    return [
        lui(T0, hi(RUNNING_THREAD)), lw(T0, T0, lo(RUNNING_THREAD)), lw(T0, T0, THREAD_ID_OFFSET),
        andi(T0, T0, HOOK_FRAME_SLOTS - 1), sll(T0, T0, 2),
        lui(T1, hi(frames)), addu(T1, T1, T0), addiu(T1, T1, lo(frames)),
        lw(T2, T1, 0), sw(T1, SP, FRAME_SLOT), sw(T2, SP, FRAME_SLOT_OLD), sw(SP, T1, 0),
    ]


def leave_slot():
    return [lw(T1, SP, FRAME_SLOT), lw(T2, SP, FRAME_SLOT_OLD), sw(T2, T1, 0)]


def entry_calls(hooks):
    words = []
    for hook in hooks:
        words += [jal(hook), NOP] + restore_args() + [ldc1(12, SP, FRAME_F12), ldc1(14, SP, FRAME_F14)]
    return words


def return_calls(hooks, frames):
    """Assumes an open frame and the function's results still in registers. Runs the hooks, leaves results restored."""
    words = save_results() + enter_slot(frames)
    for hook in hooks:
        words += [jal(hook), NOP] + restore_args() + restore_results()
    return words + leave_slot()


def entry_trampoline(func_vram, hooks, displaced, patch, return_hooks, frames):
    words = open_frame() + [sdc1(12, SP, FRAME_F12), sdc1(14, SP, FRAME_F14)] + entry_calls(hooks)
    if patch is None:
        return words + close_frame() + displaced + [j(func_vram + 8), NOP]
    if not return_hooks:
        return words + close_frame() + [j(patch), NOP]
    return words + [jal(patch), NOP] + return_calls(return_hooks, frames) + close_frame() + [JR_RA, NOP]


def return_trampoline(hooks, frames):
    return open_frame() + return_calls(hooks, frames) + close_frame() + [JR_RA, NOP]


# --- Mods ---

def load_mod(path):
    path = Path(path)
    if path.is_dir():
        syms, binary, manifest = (path / "mod_syms.bin").read_bytes(), (path / "mod_binary.bin").read_bytes(), json.loads((path / "mod.json").read_text())
    else:
        with zipfile.ZipFile(path) as z:
            syms, binary, manifest = z.read("mod_syms.bin"), z.read("mod_binary.bin"), json.loads(z.read("mod.json"))
    mod = ni.parse_syms(path.stem, syms, binary)
    mod.manifest = manifest
    mod.id = manifest["id"]
    if mod.exports or mod.events or mod.callbacks or mod.dep_events:
        fail(f"{mod.id}: exports, events and callbacks aren't supported, and neither real mod uses them")
    return mod


def relocate(mod, base, import_addr, sections_by_vrom):
    """Applies the mod's relocations for an image at `base`. Returns the new binary."""
    data = bytearray(mod.bin)
    for off, kind, target, vrom in mod.relocs:
        if vrom == ni.VROM_IMPORT:
            if kind != 4:
                fail(f"{mod.id}: reloc at {off:#x} takes the address of an import")
            addr = import_addr(target)
        elif vrom == ni.VROM_EVENT:
            fail(f"{mod.id}: reloc at {off:#x} uses an event")
        elif vrom & ni.VROM_SELF:
            if vrom != ni.VROM_SELF:
                fail(f"{mod.id}: reloc at {off:#x} targets section {vrom & ~ni.VROM_SELF}")
            addr = base + target
        else:
            sec = sections_by_vrom.get(vrom)
            if sec is None:
                fail(f"{mod.id}: reloc at {off:#x} targets unknown game section {vrom:#x}")
            addr = sec["vram"] + target

        word = struct.unpack_from(">I", data, off)[0]
        if kind == 2:
            # The word already holds the address, with its addend. The reloc's offset only names the
            # section start for merged strings, so move the word by the distance the mod moved.
            if vrom & ni.VROM_SELF:
                word = (word + base - ORIGINAL_BASE) & 0xFFFFFFFF
        elif kind == 4:
            word = (word & 0xFC000000) | ((addr & 0x0FFFFFFF) >> 2)
        elif kind == 5:
            word = (word & 0xFFFF0000) | hi(addr)
        elif kind == 6:
            word = (word & 0xFFFF0000) | lo(addr)
        else:
            fail(f"{mod.id}: unsupported relocation type {kind} at {off:#x}")
        struct.pack_into(">I", data, off, word)
    return data


def check_relocation_identity(mod, sections_by_vrom):
    """Relocating to the original address has to change nothing, apart from calls out of the mod.

    Those calls are left as zero in the binary until something links them.
    """
    import_sites = {r[0] for r in mod.relocs if r[1] == 4 and not (r[3] & ni.VROM_SELF and r[3] not in (ni.VROM_IMPORT, ni.VROM_EVENT))}
    same = relocate(mod, ORIGINAL_BASE, lambda _: 0, sections_by_vrom)
    for off in range(0, len(same) & ~3, 4):
        if off in import_sites:
            continue
        if same[off:off + 4] != mod.bin[off:off + 4]:
            fail(f"{mod.id}: relocating to the original base changes the word at {off:#x}: "
                 f"{mod.bin[off:off + 4].hex()} became {same[off:off + 4].hex()}")


# --- Config ---

def config_values(mods, overrides):
    """(mod index, key, u32, double) for each option, from mod.json defaults and --set overrides."""
    values = []
    used = set()
    for index, mod in enumerate(mods):
        schema = mod.manifest.get("config_schema", {}).get("options", [])
        for option in schema:
            key, kind = option["id"], option["type"]
            raw = overrides.get((mod.id, key), option["default"])
            if (mod.id, key) in overrides:
                used.add((mod.id, key))
            if kind == "Enum":
                choices = option["options"]
                if isinstance(raw, str) and raw in choices:
                    number = choices.index(raw)
                else:
                    try:
                        number = int(raw)
                    except ValueError:
                        fail(f"{mod.id}: {key} has no choice {raw!r}")
                    if not 0 <= number < len(choices):
                        fail(f"{mod.id}: {key} has no choice {raw!r}")
                values.append((index, key, number, float(number)))
            elif kind == "Number":
                number = float(raw)
                values.append((index, key, int(number) & 0xFFFFFFFF, number))
            else:
                fail(f"{mod.id}: config option {key} has unsupported type {kind}")
    unused = set(overrides) - used
    if unused:
        fail("--set names options that don't exist: " + ", ".join(f"{m}.{k}" for m, k in sorted(unused)))
    return values


def c_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_runtime_config(out, mods, values):
    (out / "modrt_config.h").write_text(f"""// Generated by tools/link_mods.py.
#define RT_SMOOTH_TRANSPARENCY {SMOOTH_TRANSPARENCY}

typedef struct {{
    u32 mod;
    const char* key;
    const char* keyAddr;
    u32 u;
    double d;
}} ModConfigValue;

extern ModConfigValue gModConfig[];
extern const u32 gModConfigCount;
extern const char* const gModIds[];
extern const u32 gModIdCount;
""")
    rows = "".join(f"    {{ {m}, {c_string(k)}, 0, {u}u, {d!r} }},\n" for m, k, u, d in values) or "    { 0, 0, 0, 0, 0.0 },\n"
    ids = "".join(f"    {c_string(mod.id)},\n" for mod in mods)
    (out / "modrt_config.c").write_text(f"""// Generated by tools/link_mods.py.
#include "ultra.h"
#include "modrt_config.h"

ModConfigValue gModConfig[] = {{
{rows}}};
const u32 gModConfigCount = {len(values)};
const char* const gModIds[] = {{
{ids}}};
const u32 gModIdCount = {len(mods)};
""")


def build_runtime(out, base):
    syms = out / "game_syms.ld"
    subprocess.run([sys.executable, str(ROOT / "tools/gen_game_syms.py"), str(ROOT / "vendor/Eltale-Reborn/Quest64Syms/dump.toml"), str(syms)], check=True)
    objs = []
    for src in (ROOT / "runtime/modrt.c", out / "modrt_config.c"):
        obj = out / (src.stem + ".o")
        subprocess.run(["clang", *CFLAGS, f"-I{ROOT / 'runtime'}", f"-I{out}", "-c", str(src), "-o", str(obj)], check=True)
        objs.append(str(obj))
    elf = out / "modrt.elf"
    subprocess.run(["ld.lld", "-nostdlib", f"--defsym=RT_BASE={base:#x}", f"--defsym=__osRunningThread={RUNNING_THREAD:#x}", "-T", str(syms), "-T", str(ROOT / "runtime/modrt.ld"), "-Map", str(out / "modrt.map"), *objs, "-o", str(elf)], check=True)
    binary = out / "modrt.bin"
    subprocess.run(["llvm-objcopy", "-O", "binary", "-j", ".text", str(elf), str(binary)], check=True)
    names = {}
    for line in subprocess.run(["llvm-nm", str(elf)], capture_output=True, text=True, check=True).stdout.splitlines():
        parts = line.split()
        if len(parts) == 3:
            names[parts[2]] = int(parts[0], 16)
    return binary.read_bytes(), names


# --- Hooks ---

def collect_targets(mods, hook_order, func_addr, by_key):
    """Per game function: its entry hooks, patch and return hooks, each in run order."""
    order = {mod_id: i for i, mod_id in enumerate(hook_order)}
    targets = {}

    def entry(key):
        if key not in by_key:
            fail(f"no game function at {key[1]:#x} in the section at ROM {key[0]:#x}")
        return targets.setdefault(key, {"entry": [], "return": [], "patch": None})

    for mod_index, mod in enumerate(mods):
        for func_index, vrom, vram, _flags in mod.patches:
            t = entry((vrom, vram))
            if t["patch"] is not None:
                fail(f"{by_key[(vrom, vram)].name} is patched by more than one mod")
            t["patch"] = func_addr(mod_index, func_index)
        for func_index, vrom, vram, flags in mod.hooks:
            kind = "return" if flags & ni.HOOK_AT_RETURN else "entry"
            entry((vrom, vram))[kind].append((order[mod.id], func_addr(mod_index, func_index)))
    for t in targets.values():
        t["entry"] = [addr for _, addr in sorted(t["entry"], key=lambda x: x[0])]
        t["return"] = [addr for _, addr in sorted(t["return"], key=lambda x: -x[0])]
    return targets


def check_boot_path(targets, by_key, by_name, by_vram, rom):
    """The image isn't in memory until stage 1 has loaded it, so nothing that runs before then can be hooked."""
    scans = ni.game_call_graph(by_key, rom)
    reached = set()
    for root in BOOT_ROOTS:
        reached |= ni.reachable(by_name[root].vram, by_vram, scans)
    bad = sorted(by_key[key].name for key in targets if key in reached)
    if bad:
        fail("these run before the loader has finished, so they can't be hooked or patched: " + ", ".join(bad))


def read_words(rom, func):
    return [ni.w32(rom, func.rom + i) for i in range(0, func.size, 4)]


def build_hooks(targets, by_key, rom, base, frames):
    """Generates the trampolines from `base`. Returns their words and the ROM patches."""
    code, patches = [], []

    def patch_word(func, offset, word, expect):
        patches.append({"rom": func.rom + offset, "word": word, "expect": expect, "func": func.name})

    for key in sorted(targets):
        t = targets[key]
        func = by_key[key]
        words = read_words(rom, func)
        needs_entry_rewrite = t["entry"] or t["patch"] is not None
        if needs_entry_rewrite:
            if func.size < 8:
                fail(f"{func.name} is {func.size} bytes, too short for a jump")
            if t["patch"] is None:
                for i, word in enumerate(words[:2]):
                    if ni.control_flow(word):
                        fail(f"{func.name}: instruction {i} is control flow, so it can't be displaced")
                for i, word in enumerate(words):
                    kind = ni.control_flow(word)
                    if kind == "branch" and (i + 1 + ni.sign16(word)) in (0, 1):
                        fail(f"{func.name}: a branch at +{i * 4:#x} goes into the two displaced instructions")
                    if kind == "jump" and (word >> 26) == 2 and ((word & 0x3FFFFFF) << 2 | 0x80000000) in (func.vram, func.vram + 4):
                        fail(f"{func.name}: a jump at +{i * 4:#x} goes into the two displaced instructions")
            only_jump = t["patch"] is not None and not t["entry"] and not t["return"]
            if only_jump:
                target = t["patch"]
            else:
                target = base + len(code) * 4
                code += entry_trampoline(func.vram, t["entry"], words[:2], t["patch"], t["return"], frames)
            patch_word(func, 0, j(target), words[0])
            patch_word(func, 4, NOP, words[1])
        if t["return"] and t["patch"] is None:
            sites = [i for i, word in enumerate(words) if word == JR_RA]
            if not sites:
                fail(f"{func.name} has a return hook but no jr ra")
            scan = ni.FuncScan(func, rom)
            if scan.tail_jumps:
                fail(f"{func.name} has a return hook and {scan.tail_jumps} tail jumps, which would skip it")
            target = base + len(code) * 4
            code += return_trampoline(t["return"], frames)
            for site in sites:
                if site < 2 and needs_entry_rewrite:
                    fail(f"{func.name}: jr ra at +{site * 4:#x} is among the displaced instructions")
                if site > 0 and ni.control_flow(words[site - 1]):
                    fail(f"{func.name}: jr ra at +{site * 4:#x} is in a delay slot")
                # j replaces jr ra. The delay slot stays where it is, so the trampoline sees its effect.
                patch_word(func, site * 4, j(target), JR_RA)
    return code, patches


# --- Main ---

def align(value, to):
    return (value + to - 1) & ~(to - 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mod", action="append", default=[])
    ap.add_argument("--hook-order", default=None)
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--rom", default=str(ROOT / "rom/quest64.us.z64"))
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rom = Path(args.rom).read_bytes()
    sections, by_key, by_name, by_vram = ni.load_game_funcs()
    sections_by_vrom = {sec["rom"]: sec for sec in sections}

    mods = [load_mod(path) for path in args.mod]
    ids = [mod.id for mod in mods]
    hook_order = args.hook_order.split(",") if args.hook_order else ids
    if sorted(hook_order) != sorted(ids):
        fail(f"--hook-order {hook_order} doesn't list the mods {ids}")

    overrides = {}
    for item in args.set:
        m = re.fullmatch(r"([^.=]+)\.([^=]+)=(.*)", item)
        if not m:
            fail(f"--set expects <mod id>.<option>=<value>, got {item}")
        overrides[(m.group(1), m.group(2))] = m.group(3)

    for mod in mods:
        check_relocation_identity(mod, sections_by_vrom)
        stack = ni.stack_arg_hooks(mod)
        if stack:
            names = ", ".join(f"{mod.funcs[i][0]:#x}" for i in stack)
            fail(f"{mod.id}: hooks at {names} read stack arguments, which the trampolines don't copy")

    # Lay out the mods, then the import stubs.
    cursor = IMAGE_BASE
    for mod in mods:
        mod.base = cursor
        cursor = align(cursor + mod.size + mod.bss, 16)

    stub_base = cursor
    stubs_per_mod = []
    stub_count = 0
    for mod in mods:
        table = {}
        for index, (name, dep) in enumerate(mod.imports):
            table[index] = (stub_base + stub_count * 8, name, dep)
            stub_count += 1
        stubs_per_mod.append(table)
    runtime_base = align(stub_base + stub_count * 8, 16)

    values = config_values(mods, overrides)
    write_runtime_config(out, mods, values)
    runtime, names = build_runtime(out, runtime_base)
    trampoline_base = align(runtime_base + len(runtime), 16)

    stub_words = []
    for mod_index, table in enumerate(stubs_per_mod):
        for _, name, dep in table.values():
            if dep == NATIVE_DEPENDENCY:
                stub_words += [j(names["rt_native_stub"]), NOP]
            elif name in PER_MOD_IMPORTS:
                # The mod's key is in a0, so the index goes in a1.
                stub_words += [j(names[PER_MOD_IMPORTS[name]]), addiu(A1, 0, mod_index)]
            elif name in PLAIN_IMPORTS:
                stub_words += [j(names[PLAIN_IMPORTS[name]]), NOP]
            else:
                fail(f"{mods[mod_index].id} imports {name} from {dep}, which this runtime doesn't have")

    def func_addr(mod_index, func_index):
        return mods[mod_index].base + mods[mod_index].funcs[func_index][0]

    targets = collect_targets(mods, hook_order, func_addr, by_key)
    check_boot_path(targets, by_key, by_name, by_vram, rom)
    code, patches = build_hooks(targets, by_key, rom, trampoline_base, names["rt_hook_frames"])
    end = trampoline_base + len(code) * 4
    if end > IMAGE_LIMIT:
        fail(f"the image ends at {end:#x}, past {IMAGE_LIMIT:#x}")

    image = bytearray(end - IMAGE_BASE)
    for mod_index, mod in enumerate(mods):
        linked = relocate(mod, mod.base, lambda i, t=stubs_per_mod[mod_index]: t[i][0], sections_by_vrom)
        image[mod.base - IMAGE_BASE:mod.base - IMAGE_BASE + len(linked)] = linked
    struct.pack_into(f">{len(stub_words)}I", image, stub_base - IMAGE_BASE, *stub_words)
    image[runtime_base - IMAGE_BASE:runtime_base - IMAGE_BASE + len(runtime)] = runtime
    struct.pack_into(f">{len(code)}I", image, trampoline_base - IMAGE_BASE, *code)

    (out / "image.bin").write_bytes(image)
    (out / "patches.json").write_text(json.dumps(patches, indent=1))
    layout = {
        "image_base": IMAGE_BASE,
        "image_end": end,
        "mods": [{"id": m.id, "base": m.base, "size": m.size, "bss": m.bss} for m in mods],
        "stubs": stub_base,
        "runtime": runtime_base,
        "runtime_symbols": names,
        "trampolines": trampoline_base,
        "hook_order": hook_order,
    }
    (out / "layout.json").write_text(json.dumps(layout, indent=1))
    print(f"link_mods: {len(mods)} mods, image {IMAGE_BASE:#x}-{end:#x} ({(end - IMAGE_BASE) / 1024:.1f} KB), "
          f"{len(targets)} functions, {len(patches)} ROM words, {len(code) * 4} bytes of trampolines")


if __name__ == "__main__":
    main()
