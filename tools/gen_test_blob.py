#!/usr/bin/env python3
"""Writes the Phase 1 test blob: word i is i * 0x01000193 ^ 0xE17A1E00, so a wrong copy can't look right.

The size matches what the two mods need, so the test loads as much as the real image will.

usage: gen_test_blob.py <out.bin> [size in hex]
"""

import array
import sys
from pathlib import Path

DEFAULT_SIZE = 0x150000


def word(i):
    return ((i * 0x01000193) ^ 0xE17A1E00) & 0xFFFFFFFF


def main():
    out = Path(sys.argv[1])
    size = int(sys.argv[2], 16) if len(sys.argv) > 2 else DEFAULT_SIZE
    words = array.array("I", (word(i) for i in range(size // 4)))
    if sys.byteorder == "little":
        words.byteswap()
    out.write_bytes(words.tobytes())


if __name__ == "__main__":
    main()
