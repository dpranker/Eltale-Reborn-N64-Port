#!/usr/bin/env python3
"""Turns a raw big-endian 16-bit N64 framebuffer dump into a PNG. Output is ROM-derived: keep it under build/.

usage: fb_png.py <in.bin> <width> <out.png>
"""

import struct
import sys
import zlib
from pathlib import Path


def chunk(tag, body):
    return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))


def main():
    data = Path(sys.argv[1]).read_bytes()
    width = int(sys.argv[2])
    height = len(data) // (width * 2)
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            p = struct.unpack_from(">H", data, (y * width + x) * 2)[0]
            rows += bytes((((p >> 11) & 31) * 255 // 31, ((p >> 6) & 31) * 255 // 31, ((p >> 1) & 31) * 255 // 31))
    head = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    Path(sys.argv[3]).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b""))


if __name__ == "__main__":
    main()
