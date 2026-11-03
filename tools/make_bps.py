#!/usr/bin/env python3
"""Writes a BPS patch from the vanilla ROM to a built ROM, refusing any other input ROM. IPS can't be used: it only
addresses the first 16 MB, and the mod image starts at that mark.

usage: make_bps.py --rom <vanilla> --target <built rom> --out <patch.bps>
"""

import argparse
import hashlib
import sys
import zlib

VANILLA_SHA1 = "91b96e938c6d91699057fad91d726ee5a23ce33a"
SOURCE_READ, TARGET_READ = 0, 1
MIN_SOURCE_RUN = 4  # A shorter match costs about as much to encode as its bytes do.


def number(value):
    out = bytearray()
    while True:
        low = value & 0x7F
        value >>= 7
        if value == 0:
            out.append(0x80 | low)
            return bytes(out)
        out.append(low)
        value -= 1


def action(mode, length):
    return number(((length - 1) << 2) | mode)


def encode(source, target, metadata=b""):
    """Uses only SourceRead and TargetRead: the port changes bytes in place and appends the rest."""
    out = bytearray(b"BPS1")
    out += number(len(source)) + number(len(target)) + number(len(metadata)) + metadata
    position, pending = 0, 0
    shared = min(len(source), len(target))
    while position < len(target):
        run = 0
        while position + run < shared and source[position + run] == target[position + run]:
            run += 1
        if run >= MIN_SOURCE_RUN:
            if pending:
                out += action(TARGET_READ, pending) + target[position - pending:position]
                pending = 0
            out += action(SOURCE_READ, run)
            position += run
        else:
            step = max(run, 1)
            pending += step
            position += step
    if pending:
        out += action(TARGET_READ, pending) + target[position - pending:position]
    out += zlib.crc32(source).to_bytes(4, "little") + zlib.crc32(target).to_bytes(4, "little")
    out += zlib.crc32(out).to_bytes(4, "little")
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    source = open(args.rom, "rb").read()
    if hashlib.sha1(source).hexdigest() != VANILLA_SHA1:
        sys.exit(f"make_bps: {args.rom} isn't the US Quest 64 ROM (SHA-1 {VANILLA_SHA1})")
    target = open(args.target, "rb").read()
    patch = encode(source, target)
    open(args.out, "wb").write(patch)
    print(f"make_bps: {args.out}: {len(patch)} bytes, target SHA-1 {hashlib.sha1(target).hexdigest()}")


if __name__ == "__main__":
    main()
