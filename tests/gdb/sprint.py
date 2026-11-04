# D-Pad Up turns sprint on and off while Brian can move, and does nothing in menus, which use the D-pad. L stays free
# for the camera.
gdb.execute("source tests/gdb/dl_common.py")

SPRINT_ON = layout["runtime_symbols"]["rt_sprint_on"]


def sprint_on():
    return inferior.read_memory(0xA0000000 | (SPRINT_ON & 0x1FFFFFFF), 1).tobytes()[0] != 0


title_to_new_game()
talk(6000)
set_flag(16)
clear_scene()
warp(2)
wait_polls(60)
check(not sprint_on(), "sprint starts off")
print(f"AT field: mode {read16(GAME_MODE)}, game state {read32(GAME_STATE):#x}, player state {read16(PLAYER_STATE)}", flush=True)

walk = speed((0, -80), frames=8)
press(L)
check(not sprint_on(), "L doesn't touch sprint")
press(DUP)
check(sprint_on(), "D-Pad Up turns sprint on")
run = speed((0, -80), frames=8)     # The same way: back past the entry point is the exit.
print(f"AT walk {walk:.3f} sprint {run:.3f}", flush=True)
check(run > walk * 1.2, f"sprinting is faster: {run:.3f} against {walk:.3f}")
press(DUP)
check(not sprint_on(), "D-Pad Up turns sprint off")

for name, button in (("item menu", R), ("Start menu", START)):
    press(button, frames=3, after=30)
    print(f"AT {name}: mode {read16(GAME_MODE)}, game state {read32(GAME_STATE):#x}, player state {read16(PLAYER_STATE)}", flush=True)
    shot("sprint_" + name.split()[0].lower())
    press(DUP, frames=3, after=10)
    check(not sprint_on(), f"D-Pad Up in the {name} leaves sprint off")
    for _ in range(10):
        if free() and read16(GAME_MODE) == MODE_FIELD:
            break
        press(B, frames=3, after=20)
    check(free() and read16(GAME_MODE) == MODE_FIELD, f"the {name} closed")
    if sprint_on():                    # Don't let one failure run on into the next check.
        press(DUP)
    press(DUP)
    check(sprint_on(), f"D-Pad Up works again after the {name}")
    press(DUP)

warp(2)
to_battle_point()
wait_polls(5)
force_battle()
stay_alive()
wait_polls(60)
before = sprint_on()
press(DUP)
print(f"AT battle: sprint {before} then {sprint_on()}, mode {read16(GAME_MODE)}, game state {read32(GAME_STATE):#x}, player state {read16(PLAYER_STATE)}", flush=True)
check(not faults, "no CPU faults")
finish()
