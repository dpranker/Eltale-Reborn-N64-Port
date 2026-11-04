# Display list checks over the scenes this route reaches. Each scene takes a frame standing and one while walking.
gdb.execute("source tests/gdb/dl_common.py")
CROWD = os.environ.get("PERF_CROWD")


def two(name, stick=(0, -70)):
    capture(name)
    write32(STICK, ((stick[0] & 0xFF) << 8) | (stick[1] & 0xFF))
    wait_polls(30)
    capture(name + "_walking")
    write32(STICK, 0)
    wait_polls(5)


if TARGET == "eltale":
    title_to_new_game()
    capture("opening")
    talk(6000)
    set_flag(16)
else:
    new_game()
clear_scene()

warp(0x0D, 9)
wait_polls(120)
capture("monastery_corridor")

melrode_street()
two("melrode_street")
clear_scene()
if TARGET == "eltale":
    addr = FLAGS + 0x74 // 8           # Nine of the street's people, as in tests/gdb/perf_moving.py.
    inferior.write_memory(addr, bytes([inferior.read_memory(addr, 1).tobytes()[0] & ~(1 << (0x74 % 8)) & 0xFF]))
    warp(0x1A)
    melrode_street()
    two("melrode_crowd")
    clear_scene()
    set_flag(0x74)

warp(0x1A)
wait_polls(120)
capture("blue_cave")

warp(2)
wait_polls(120)
two("holy_plain")
clear_scene()

warp(2)
to_battle_point()
wait_polls(5)
force_battle()
stay_alive()
wait_polls(60)
capture("battle_start")
stay_alive()
wait_polls(120)
capture("battle")
stay_alive()
hold(A, frames=3)
wait_polls(20)
capture("battle_swing")

if TARGET == "eltale":
    while read16(BATTLE_STATE) & 1:
        write16(0x8007C998 + 0xA, 0)
        stay_alive()
        hold(A, frames=3)
        wait_polls(30)
    clear_scene()
    set_flag(16)
    melrode_street()
    place(12, 590, 12, 645)
    wait_polls(60)
    capture("farewell_scene")
    for i in range(4):
        hold(A, frames=3)
        wait_polls(60)
        capture(f"farewell_scene_{i}")

check(not faults, "no CPU faults")
check(not any(row["problems"] for row in checked), "no display list problems")
limit = 2560                       # Past this, a list writes over the next frame's task. See tests/gdb/glencoe.py.
peak = max(row["list_peak"] for row in checked)
print(f"RESULT list peak {peak} commands of {limit}", flush=True)
check(peak * 10 <= limit * 9, f"the list stays under 90% of its buffer: {peak} of {limit}")
finish()
