#!/usr/bin/env python3
"""Writes a linker script of the game's .main function addresses, so runtime C can call them.

usage: gen_game_syms.py <dump.toml> <out.ld>
"""

import sys
import tomllib
from pathlib import Path


def main():
    dump, out = sys.argv[1:3]
    with open(dump, "rb") as f:
        syms = tomllib.load(f)
    lines = []
    for sec in syms["section"]:
        if sec["name"] != ".main":
            continue
        for fn in sec["functions"]:
            lines.append(f"{fn['name']} = 0x{fn['vram']:08X};")
    Path(out).write_text("\n".join(sorted(lines)) + "\n")


if __name__ == "__main__":
    main()
