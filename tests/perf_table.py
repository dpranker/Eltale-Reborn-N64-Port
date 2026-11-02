#!/usr/bin/env python3
"""Prints the frame-time scenes from tests/gdb/perf.py side by side. usage: perf_table.py <vanilla log> <eltale log>"""

import json
import sys


def scenes(path):
    return {s["scene"]: s for s in (json.loads(line[6:]) for line in open(path) if line.startswith("SCENE "))}


vanilla, eltale = scenes(sys.argv[1]), scenes(sys.argv[2])
print(f"{'scene':<22}{'':<9}{'fps':>6}{'worst':>7}{'game%':>7}{'peak%':>7}{'rcp%':>6}{'peak%':>7}{'cmds':>7}{'people':>7}")
for name in list(vanilla) + [n for n in eltale if n not in vanilla]:
    for label, row in (("vanilla", vanilla.get(name)), ("eltale", eltale.get(name))):
        if row:
            print(f"{name:<22}{label:<9}{row['fps']:>6.1f}{row['worst']:>7}{row['game']:>7.0f}{row['game_peak']:>7.0f}"
                  f"{row['rcp']:>6.0f}{row['rcp_peak']:>7.0f}{row['commands']:>7}{row['people']:>7}")
