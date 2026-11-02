#!/usr/bin/env python3
"""Prints the frames from tests/gdb/dl_scenes.py, then each kind of problem. usage: dl_table.py <log>"""

import json
import sys

rows = [json.loads(line[3:]) for line in open(sys.argv[1]) if line.startswith("DL ")]
print(f"{'scene':<26}{'target':<9}{'tasks':>6}{'cmds':>7}{'tris':>6}{'drawn':>7}{'off':>6}{'cull':>6}{'kpix':>7}{'rdp%':>6}{'2cyc%':>6}{'load':>6}{'depth':>6}{'mod':>5}")
for r in rows:
    two = r["two_cycle_pixels"] / r["pixels"] * 100 if r["pixels"] else 0
    print(f"{r['scene']:<26}{r['target']:<9}{r['tasks']:>6}{r['commands']:>7}{r['triangles']:>6}{r['drawn']:>7}{r['off_screen']:>6}{r['culled']:>6}"
          f"{r['pixels'] / 1000:>7.0f}{r['rdp_best_case_percent']:>6.0f}{two:>6.0f}{r['largest_load']:>6}{r['deepest']:>6}{r['mod_lists']:>5}")
seen = {}
for r in rows:
    for p in r["problems"]:
        key = (p["kind"], p["at"], p["detail"])
        seen.setdefault(key, []).append(r["scene"])
for (kind, at, detail), scenes in sorted(seen.items()):
    print(f"PROBLEM {kind} at {at} {detail}: {', '.join(sorted(set(scenes)))[:120]}")
if not seen:
    print("no problems")
