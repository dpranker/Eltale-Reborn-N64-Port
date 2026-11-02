#!/usr/bin/env python3
"""Compares Phase 3 measurements from vanilla and modded runs against the gameplay mod's defaults.

usage: compare_phase3.py <vanilla log> <gameplay log> <idle log>
"""

import sys
from pathlib import Path

SPRINT_RATE = 1.25
ENCOUNTER_RATE = 0.5
EXP_RATE = 2.0
# At 30 polls a second, ten minutes.
IDLE_POLLS = 18000


def metrics(path):
    found = {}
    for line in Path(path).read_text().splitlines():
        if line.startswith("METRIC "):
            _, name, value = line.split()
            found[name] = float(value)
    return found


def main():
    vanilla, gameplay, idle = (metrics(p) for p in sys.argv[1:4])
    failures = 0

    def check(ok, text):
        nonlocal failures
        print(("ok: " if ok else "FAIL: ") + text)
        failures += not ok

    def near(value, want, tolerance):
        return abs(value - want) <= tolerance

    for name, run in (("vanilla", vanilla), ("gameplay", gameplay)):
        check(run.get("battle_started") == 1, f"{name}: a battle started")
    check(near(vanilla["walk_speed"], gameplay["walk_speed"], 0.05), f"walk speed is unchanged: {vanilla['walk_speed']:.3f} and {gameplay['walk_speed']:.3f}")
    check(near(vanilla["sprint_speed"] / vanilla["walk_speed"], 1.0, 0.03), f"vanilla ignores the sprint bit: {vanilla['sprint_speed'] / vanilla['walk_speed']:.3f}")
    ratio = gameplay["sprint_speed"] / gameplay["walk_speed"]
    check(near(ratio, SPRINT_RATE, 0.03), f"sprint is x{SPRINT_RATE}: measured x{ratio:.3f}")
    ratio = gameplay["sprint_button_speed"] / gameplay["walk_speed"]
    check(near(ratio, SPRINT_RATE, 0.03), f"the L button sprints: measured x{ratio:.3f}")
    ratio = vanilla["sprint_button_speed"] / vanilla["walk_speed"]
    check(near(ratio, 1.0, 0.03), f"L doesn't sprint without the mod: measured x{ratio:.3f}")
    ratio = gameplay["encounter_meter_per_step"] / vanilla["encounter_meter_per_step"]
    check(near(ratio, ENCOUNTER_RATE, 0.05), f"the encounter meter fills at x{ENCOUNTER_RATE}: measured x{ratio:.3f}")
    check(vanilla["exp_gained"] > 0, f"vanilla gained EXP: {vanilla['exp_gained']:.0f}")
    ratio = gameplay["exp_gained"] / vanilla["exp_gained"] if vanilla["exp_gained"] else 0
    check(near(ratio, EXP_RATE, 0.01), f"EXP is x{EXP_RATE} from the same fight: {gameplay['exp_gained']:.0f} against {vanilla['exp_gained']:.0f}")
    check(idle.get("idle_polls", 0) >= IDLE_POLLS, f"idled for at least ten game minutes: {idle.get('idle_polls', 0):.0f} polls")
    check(idle.get("idle_alive_after", 0) >= 30, "the game was still polling input afterwards")
    print("PHASE 3 AUTOMATED CHECKS PASS" if not failures else "PHASE 3 AUTOMATED CHECKS FAIL")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
