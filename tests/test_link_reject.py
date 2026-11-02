#!/usr/bin/env python3
"""The engine must refuse functions it can't hook safely, loudly, rather than patch them badly."""

import contextlib
import io
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import link_mods as lm
import nrm_inspect as ni

SECTION = {"name": ".main", "rom": 0, "vram": 0x80000000, "size": 0x100}
NOP = 0
ADDIU_SP = lm.addiu(lm.SP, lm.SP, -0x18)
JR_RA = lm.JR_RA
BEQ_FORWARD = (4 << 26) | 2


def attempt(words, entry=(), returns=()):
    rom = struct.pack(f">{len(words)}I", *words)
    func = ni.Func("func_test", 0x80000000, len(words) * 4, SECTION)
    key = (0, 0x80000000)
    targets = {key: {"entry": list(entry), "return": list(returns), "patch": None}}
    return lm.build_hooks(targets, {key: func}, rom, 0x80500000, 0x80600000)


def rejected(name, words, **kw):
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            attempt(words, **kw)
    except SystemExit as e:
        print(f"ok: {name}: {e.code}")
        return True
    print(f"FAIL: {name} was accepted")
    return False


def main():
    results = [
        rejected("branch in the displaced instructions", [BEQ_FORWARD, NOP, NOP, JR_RA, NOP], entry=[0x80400000]),
        rejected("jump in the displaced instructions", [ADDIU_SP, lm.jal(0x80001000), NOP, JR_RA, NOP], entry=[0x80400000]),
        rejected("branch back into the displaced instructions", [ADDIU_SP, NOP, NOP, (4 << 26) | 0xFFFC, NOP, JR_RA, NOP], entry=[0x80400000]),
        rejected("too short for a jump", [JR_RA], entry=[0x80400000]),
        rejected("return hook with no jr ra", [ADDIU_SP, NOP, NOP, NOP], returns=[0x80400000]),
        rejected("return hook with a tail jump", [ADDIU_SP, lm.j(0x80002000), NOP, JR_RA, NOP], returns=[0x80400000]),
        rejected("jr ra in a delay slot", [ADDIU_SP, NOP, BEQ_FORWARD, JR_RA, NOP], returns=[0x80400000]),
    ]
    code, patches = attempt([ADDIU_SP, NOP, NOP, JR_RA, NOP], entry=[0x80400000], returns=[0x80400100])
    good = code and len(patches) == 3
    print("ok: a clean function is accepted" if good else "FAIL: a clean function wasn't accepted")
    results.append(good)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
