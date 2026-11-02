#!/usr/bin/env python3
"""Disassembles a game function or address range from the ROM, for reading only. Never commit the output.

usage: rom_dis.py <function name | vram> [size in hex] [--section .main]
"""

import argparse
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target")
    ap.add_argument("size", nargs="?")
    ap.add_argument("--section", default=None)
    ap.add_argument("--rom", default=str(ROOT / "rom/quest64.us.z64"))
    args = ap.parse_args()

    with open(ROOT / "vendor/Eltale-Reborn/Quest64Syms/dump.toml", "rb") as f:
        syms = tomllib.load(f)
    names, by_vram, found = {}, {}, None
    for sec in syms["section"]:
        for fn in sec.get("functions", []):
            names[fn["vram"]] = fn["name"]
            if fn["name"] == args.target:
                found = (sec, fn["vram"], fn["size"])
    if found is None:
        vram = int(args.target, 16)
        for sec in syms["section"]:
            if sec["vram"] <= vram < sec["vram"] + sec["size"] and (not args.section or sec["name"] == args.section):
                found = (sec, vram, 0x40)
                break
    if found is None:
        sys.exit(f"rom_dis: no function or section holds {args.target}")
    sec, vram, size = found
    if args.size:
        size = int(args.size, 16)

    rom = Path(args.rom).read_bytes()
    start = sec["rom"] + vram - sec["vram"]
    with tempfile.TemporaryDirectory() as tmp:
        raw, obj = Path(tmp) / "code.bin", Path(tmp) / "code.o"
        raw.write_bytes(rom[start:start + size])
        subprocess.run(["llvm-objcopy", "-I", "binary", "-O", "elf32-tradbigmips", "--rename-section", ".data=.text,code", str(raw), str(obj)], check=True)
        out = subprocess.run(["llvm-objdump", "-d", "--no-show-raw-insn", "--triple=mips-unknown-linux-gnu", "--mcpu=mips3", str(obj)], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines()[6:]:
        off, _, rest = line.partition(":")
        if not off.strip() or not rest.strip():
            continue
        text = rest.split("<")[0].strip().replace("\t", " ")
        parts = text.split()
        note = ""
        if parts and parts[0] in ("jal", "j"):
            target = int(parts[1], 16) | 0x80000000 | (vram & 0x70000000)
            note = f"  ; {target:#x} {names.get(target, '')}"
        print(f"{vram + int(off, 16):08X}: {text}{note}")


if __name__ == "__main__":
    main()
