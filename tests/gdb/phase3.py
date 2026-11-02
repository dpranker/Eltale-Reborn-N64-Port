# Measures what the gameplay mod changes. tests/run_phase3.sh runs this on vanilla and modded ROMs and compares.
gdb.execute("source tests/gdb/phase3_common.py")
import statistics
new_game()
metric("reached_free_movement", 1)

# Field speed on the monastery's flat floor, back and forth. Short walks stay clear of the walls.
walks, sprints = [], []
for stick in ((0, -80), (0, 80), (0, -80), (0, 80)):
    walks.append(speed(stick, frames=8))
    sprints.append(speed((-stick[0], -stick[1]), buttons=SPRINT_BIT, frames=8))
print("walks", [round(v, 3) for v in walks], "sprints", [round(v, 3) for v in sprints], flush=True)
metric("walk_speed", max(walks))
metric("sprint_speed", max(sprints))
shoulder = []
for stick in ((0, -80), (0, 80), (0, -80), (0, 80)):
    shoulder.append(speed(stick, buttons=L, frames=8))
print("with L", [round(v, 3) for v in shoulder], flush=True)
metric("sprint_button_speed", max(shoulder))

warp(2)                                      # Holy Plain
metric("map", read32(NEXT_MAP))
shot("p3_plain_" + TAG)

# The encounter meter gains the game's step value each frame, scaled by the mod. It restarts at 50 units, so
# sample short walks from zero, and compare with the steps the game itself computed.
ratios = []
for stick in ((80, 0), (-80, 0), (80, 0), (-80, 0), (80, 0), (-80, 0)):
    write32(STICK, ((stick[0] & 0xFF) << 8) | (stick[1] & 0xFF))
    wait_polls(10)
    write_float(ENCOUNTER_DIST, 0.0)
    steps = 0.0
    for _ in range(6):
        wait_polls(1)
        steps += read_float(ENCOUNTER_STEP)
    meter = read_float(ENCOUNTER_DIST)
    write32(STICK, 0)
    wait_polls(10)
    if steps > 3:
        ratios.append(meter / steps)
print("meter/steps", [round(v, 3) for v in ratios], flush=True)
metric("encounter_meter_per_step", statistics.median(ratios) if ratios else 0)

# A pinned battle, won with the staff and magic. Warp again, because the walks may have left the battle zone.
warp(2)
to_battle_point()
wait_polls(5)
force_battle()
wait_polls(90)
shot("p3_battle_" + TAG)
metric("battle_started", 1)
exp_before = read32(EXP)
ENEMY = 0x8007C998
for i in range(120):
    # This measures EXP, not the fight: Brian stays healthy, and one hit ends it.
    write16(0x8007BA84, read16(0x8007BA86))
    write16(0x8007BA88, read16(0x8007BA8A))
    write16(ENEMY + 0xA, 1)
    # Stand next to the enemy, facing it, so the staff connects with either aiming mode.
    ex, ez = read_float(ENEMY + 0x24), read_float(ENEMY + 0x2C)
    bx, bz = position()
    away = math.hypot(bx - ex, bz - ez)
    if away > 25 and away > 0:
        write_float(PLAYER, ex + (bx - ex) / away * 15)
        write_float(PLAYER + 8, ez + (bz - ez) / away * 15)
    write_float(PLAYER + 0x10, math.atan2(ex - bx, ez - bz))
    hold(A, frames=3)
    wait_polls(30)
    if i == 2:
        shot("p3_fight_" + TAG)
    if not read16(BATTLE_STATE) & 1 or read32(EXP) != exp_before:
        break
wait_polls(60)
shot("p3_after_" + TAG)
metric("battle_turns", i)
metric("battle_state", read16(BATTLE_STATE))
metric("exp_gained", read32(EXP) - exp_before)
metric("game_state", read32(GAME_STATE))
report_stacks()
metric("cpu_faults", len(faults))
finish()
