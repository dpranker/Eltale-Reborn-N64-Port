gdb.execute("source tests/gdb/perf_common.py")
if TARGET == "eltale":
    title_to_new_game()
    measure("opening", 120)
    talk(6000)
    set_flag(16)                   # skip the monastery goodbyes
else:
    new_game()
clear_scene()

warp(0x0D, 9)                      # the monastery's dormitory corridor, so both ROMs measure the same room
wait_polls(120)
measure("monastery_corridor")

melrode_street()
walk_back_and_forth("melrode_walk", seconds=2)    # The Dreamcast notes put a house door about 3 s up this walk.
melrode_street()
measure("melrode_street")
check(melrode_crowd() > 0, "Melrode has people on the street")

clear_scene()
warp(0x1A)
wait_polls(120)
measure("blue_cave")

warp(2)
wait_polls(120)
measure("holy_plain")
walk_back_and_forth("holy_plain_walk")

warp(2)
to_battle_point()
wait_polls(5)
force_battle()
wait_polls(60)
stay_alive()
reset()
for _ in range(10):
    stay_alive()
    wait_polls(30)
report("battle")

if TARGET == "eltale":
    # The heaviest scene the route reaches: the village seeing Brian off on Melrode's road.
    while read16(BATTLE_STATE) & 1:
        write16(0x8007C998 + 0xA, 0)
        stay_alive()
        hold(A, frames=3)
        wait_polls(30)
    set_flag(16)
    warp(0)
    wait_polls(30)
    place(12, 590, 12, 645)
    wait_polls(30)
    reset()
    ok = talk(3600)
    check(ok, "the farewell scene finishes")
    report("farewell_scene")
    # The street after the farewell, for a fuller town than the prologue's evening.
    melrode_street()
    print(f"AT after farewell: flags={read32(FLAGS):08x} people={read32(NPC_COUNT)}", flush=True)
    measure("melrode_street_after")
    melrode_crowd()

check(not faults, "no CPU faults")
finish()
