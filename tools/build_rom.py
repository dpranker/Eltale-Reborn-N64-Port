#!/usr/bin/env python3
"""Goes from the vanilla ROM to a patched ROM: links the mods, builds stage 1 for that image, patches the ROM.

usage: build_rom.py --out <dir> --name <rom name> --mod <.nrm or dir>... [--hook-order a,b] [--set mod.key=value]...
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFLAGS = ["-target", "mips", "-mips2", "-mabi=32", "-O2", "-G0", "-mno-abicalls", "-mno-odd-spreg",
          "-mno-check-zero-division", "-fno-pic", "-ffreestanding", "-fno-builtin", "-fomit-frame-pointer",
          "-fno-stack-protector", "-ffunction-sections", "-Wall", "-Wextra", "-Werror"]
ROM_ADDR = 0x1000000
RAM_ADDR = 0x80400000
MAGIC_ADDR = 0x807FFFF0


def run(*cmd):
    subprocess.run([str(c) for c in cmd], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--mod", action="append", default=[])
    ap.add_argument("--hook-order", default=None)
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--rom", default=str(ROOT / "rom/quest64.us.z64"))
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    link = [sys.executable, ROOT / "tools/link_mods.py", "--out", out, "--rom", args.rom]
    for mod in args.mod:
        link += ["--mod", mod]
    if args.hook_order:
        link += ["--hook-order", args.hook_order]
    for item in args.set:
        link += ["--set", item]
    run(*link)

    size = (out / "image.bin").stat().st_size
    (out / "loader_config.h").write_text(
        f"#define LOADER_ROM_ADDR {ROM_ADDR:#x}\n#define LOADER_RAM_ADDR {RAM_ADDR:#x}\n"
        f"#define LOADER_MAGIC_ADDR {MAGIC_ADDR:#x}\n#define LOADER_SIZE {size}\n")
    run("clang", *CFLAGS, f"-I{out}", f"-I{ROOT / 'runtime'}", "-c", ROOT / "runtime/loader.c", "-o", out / "loader.o")
    run("ld.lld", "-nostdlib", "-T", out / "game_syms.ld", "-T", ROOT / "runtime/loader.ld", "-Map", out / "stage1.map", out / "loader.o", "-o", out / "stage1.elf")
    run("llvm-objcopy", "-O", "binary", "-j", ".text", out / "stage1.elf", out / "stage1.bin")

    run(sys.executable, ROOT / "tools/patch_rom.py", "--rom", args.rom, "--stage1", out / "stage1.bin", "--blob", out / "image.bin",
        "--patches", out / "patches.json", "--out", out / f"{args.name}.z64")

    # Addresses for gdb scripts, kept under build/.
    layout = json.loads((out / "layout.json").read_text())
    lines = [f"set ${name} = {addr:#x}" for name, addr in layout["runtime_symbols"].items() if name.startswith("rt_")]
    (out / "syms.gdb").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
