#!/usr/bin/env python3
"""Decodes BPS patches from the format's description, sharing no code with tools/make_bps.py, so an encoder mistake
can't hide in a shared helper. usage: test_bps.py [<vanilla> <built rom> <patch.bps>]"""

import random
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import make_bps


def apply_patch(patch, source):
    if patch[:4] != b"BPS1":
        raise ValueError("bad magic")
    if zlib.crc32(patch[:-4]) != int.from_bytes(patch[-4:], "little"):
        raise ValueError("patch CRC")
    if zlib.crc32(source) != int.from_bytes(patch[-12:-8], "little"):
        raise ValueError("source CRC")
    at = 4

    def read_number():
        nonlocal at
        result, shift = 0, 1
        while True:
            byte = patch[at]
            at += 1
            result += (byte & 0x7F) * shift
            if byte & 0x80:
                return result
            shift <<= 7
            result += shift

    if read_number() != len(source):
        raise ValueError("source size")
    target_size = read_number()
    metadata_size = read_number()
    at += metadata_size
    out = bytearray()
    source_rel = target_rel = 0
    while at < len(patch) - 12:
        word = read_number()
        mode, length = word & 3, (word >> 2) + 1
        if mode == 0:
            out += source[len(out):len(out) + length]
        elif mode == 1:
            out += patch[at:at + length]
            at += length
        else:
            step = read_number()
            step = -(step >> 1) if step & 1 else step >> 1
            if mode == 2:
                source_rel += step
                out += source[source_rel:source_rel + length]
                source_rel += length
            else:
                target_rel += step
                for _ in range(length):
                    out.append(out[target_rel])
                    target_rel += 1
    if len(out) != target_size or zlib.crc32(out) != int.from_bytes(patch[-8:-4], "little"):
        raise ValueError("target size or CRC")
    return bytes(out)


failures = 0


def check(ok, text):
    global failures
    print(("ok: " if ok else "FAIL: ") + text)
    failures += not ok


# Values from the format's number coding: 0 is 0x80, 127 is 0xFF, 128 is 0x00 0x80, 16512 is 0x00 0x00 0x80.
check(make_bps.number(0) == b"\x80" and make_bps.number(127) == b"\xff", "one-byte numbers")
check(make_bps.number(128) == b"\x00\x80" and make_bps.number(16512) == b"\x00\x00\x80", "numbers past a byte")
rng = random.Random(64)
for name, source, target in (
    ("identical", b"abcdefgh" * 50, b"abcdefgh" * 50),
    ("changed in place", b"\0" * 500, b"\0" * 100 + b"XY" + b"\0" * 398),
    ("appended", b"same" * 100, b"same" * 100 + b"new data"),
    ("shortened", b"0123456789" * 40, b"0123456789" * 20),
    ("short match", b"abcabcabc", b"abXabYabZ"),
    ("empty source", b"", b"all new"),
):
    check(apply_patch(make_bps.encode(source, target), source) == target, f"round trip: {name}")
for i in range(50):
    source = bytes(rng.randrange(4) for _ in range(rng.randrange(1, 3000)))
    target = bytearray(source)
    for _ in range(rng.randrange(40)):
        target[rng.randrange(len(target))] = rng.randrange(256)
    target += bytes(rng.randrange(256) for _ in range(rng.randrange(300)))
    if apply_patch(make_bps.encode(source, bytes(target)), source) != bytes(target):
        check(False, f"random round trip {i}")
        break
else:
    check(True, "50 random round trips")
good = make_bps.encode(b"source bytes", b"target bytes")
for label, patch, source in (("wrong source", good, b"source byteZ"), ("damaged patch", good[:6] + b"\x7f" + good[7:], b"source bytes")):
    try:
        apply_patch(patch, source)
        check(False, f"{label} is refused")
    except ValueError:
        check(True, f"{label} is refused")
if len(sys.argv) == 4:
    source, target, patch = (open(path, "rb").read() for path in sys.argv[1:])
    check(apply_patch(patch, source) == target, f"the real patch rebuilds the ROM: {len(patch)} bytes to {len(target)}")
print("BPS TESTS PASS" if not failures else "BPS TESTS FAIL")
sys.exit(1 if failures else 0)
