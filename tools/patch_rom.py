#!/usr/bin/env python3
"""Builds a patched ROM from the vanilla one: appends the blob, installs stage 1, fixes the checksum.

usage: patch_rom.py --rom <vanilla.z64> --stage1 <stage1.bin> --blob <blob.bin> [--patches <patches.json>] --out <out.z64>
"""

import argparse
import hashlib
import json
import struct
import sys
import tomllib
from pathlib import Path

import n64crc

ROOT = Path(__file__).resolve().parent.parent
VANILLA_SHA1 = "91b96e938c6d91699057fad91d726ee5a23ce33a"
STAGE1_VRAM = 0x800471B0
STAGE1_MAX = 0x6A4
# The jal osCreatePiManager in func_800004B0.
BOOT_CALL_VRAM = 0x800004D0
OS_CREATE_PI_MANAGER = 0x80033D80
BLOB_ROM_ADDR = 0x1000000
ROM_ALIGN = 0x100000


def fail(msg):
    sys.exit(f"patch_rom: error: {msg}")


def jal(vram):
    return 0x0C000000 | ((vram & 0x0FFFFFFF) >> 2)


def rom_offset(sections, vram):
    for sec in sections:
        if sec["name"] in (".entry", ".main") and sec["vram"] <= vram < sec["vram"] + sec["size"]:
            return sec["rom"] + vram - sec["vram"]
    fail(f"{vram:#x} isn't in .entry or .main")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", required=True)
    ap.add_argument("--stage1", required=True)
    ap.add_argument("--blob", required=True)
    ap.add_argument("--patches", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rom = bytearray(Path(args.rom).read_bytes())
    if hashlib.sha1(rom).hexdigest() != VANILLA_SHA1:
        fail(f"{args.rom} isn't the US Quest 64 ROM (SHA-1 {VANILLA_SHA1})")
    with open(ROOT / "vendor/Eltale-Reborn/Quest64Syms/dump.toml", "rb") as f:
        sections = tomllib.load(f)["section"]

    stage1 = Path(args.stage1).read_bytes()
    if len(stage1) > STAGE1_MAX:
        fail(f"stage 1 is {len(stage1):#x} bytes, the limit is {STAGE1_MAX:#x}")
    start = rom_offset(sections, STAGE1_VRAM)
    rom[start:start + STAGE1_MAX] = stage1.ljust(STAGE1_MAX, b"\0")

    call = rom_offset(sections, BOOT_CALL_VRAM)
    if struct.unpack_from(">I", rom, call)[0] != jal(OS_CREATE_PI_MANAGER):
        fail(f"the word at {BOOT_CALL_VRAM:#x} isn't the expected call")
    struct.pack_into(">I", rom, call, jal(STAGE1_VRAM))

    # Hook and patch words from link_mods.py. Each records what it expects to replace.
    patches = json.loads(Path(args.patches).read_text()) if args.patches else []
    seen = set()
    for patch in patches:
        if patch["rom"] in seen:
            fail(f"two patches write ROM {patch['rom']:#x} in {patch['func']}")
        seen.add(patch["rom"])
        if struct.unpack_from(">I", rom, patch["rom"])[0] != patch["expect"]:
            fail(f"the word at ROM {patch['rom']:#x} in {patch['func']} isn't what the patch expects")
        struct.pack_into(">I", rom, patch["rom"], patch["word"])

    blob = Path(args.blob).read_bytes()
    if len(rom) != BLOB_ROM_ADDR:
        fail(f"expected a {BLOB_ROM_ADDR:#x}-byte ROM")
    rom += blob
    rom += b"\xFF" * (-len(rom) % ROM_ALIGN)

    n64crc.fix(rom)
    Path(args.out).write_bytes(rom)
    print(f"patch_rom: {args.out}: {len(rom):#x} bytes, stage 1 {len(stage1):#x}, blob {len(blob):#x} at ROM {BLOB_ROM_ADDR:#x}")


if __name__ == "__main__":
    main()
