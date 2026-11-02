#!/usr/bin/env python3
"""The N64 header checksum for CIC-6102, the chip this game uses.

Used as a module by patch_rom.py. Run directly, it checks a ROM's header: exit status 0 if it matches.

usage: n64crc.py <rom.z64>
"""

import hashlib
import struct
import sys
from pathlib import Path

# MD5 of the boot code (ROM 0x40-0xFFF) of a CIC-6102 game. Checksums here are only right for that chip.
IPL3_6102_MD5 = "e24dd796b2fa16511521139d28c8356b"
SEED_6102 = 0xF8CA4DDC
MASK = 0xFFFFFFFF
CRC_START = 0x1000
CRC_LENGTH = 0x100000


def compute(rom):
    if hashlib.md5(rom[0x40:0x1000]).hexdigest() != IPL3_6102_MD5:
        raise ValueError("the boot code isn't CIC-6102's")
    t1 = t2 = t3 = t4 = t5 = t6 = SEED_6102
    for off in range(CRC_START, CRC_START + CRC_LENGTH, 4):
        d = struct.unpack_from(">I", rom, off)[0]
        if (t6 + d) & MASK < t6:
            t4 = (t4 + 1) & MASK
        t6 = (t6 + d) & MASK
        t3 ^= d
        shift = d & 31
        r = ((d << shift) | (d >> (32 - shift))) & MASK if shift else d
        t5 = (t5 + r) & MASK
        t2 = t2 ^ r if t2 > d else t2 ^ (t6 ^ d)
        t1 = (t1 + (t5 ^ d)) & MASK
    return t6 ^ t4 ^ t3, t5 ^ t2 ^ t1


def fix(rom):
    """Writes the checksum into a bytearray ROM's header."""
    struct.pack_into(">II", rom, 0x10, *compute(rom))


def main():
    rom = Path(sys.argv[1]).read_bytes()
    crc1, crc2 = compute(rom)
    have1, have2 = struct.unpack_from(">II", rom, 0x10)
    print(f"computed {crc1:08X} {crc2:08X}, header {have1:08X} {have2:08X}")
    sys.exit(0 if (crc1, crc2) == (have1, have2) else 1)


if __name__ == "__main__":
    main()
