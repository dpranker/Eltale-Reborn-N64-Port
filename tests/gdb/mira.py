# Plays the village farewell and Mira on the road, capturing frames throughout, so her custom model can be looked at.
gdb.execute("source tests/gdb/dl_common.py")
os.makedirs(f"{ROOT}/build/shots/ares", exist_ok=True)
title_to_new_game()
talk(6000)
set_flag(16)
clear_scene()
melrode_street()
place(12, 590, 12, 645)
wait_polls(75)
n = 0
free_for = 0
for i in range(400):
    if free():
        free_for += 1
        if free_for == 3:
            place(12, 595, 12, 645)        # Her scene may wait for Brian to step in again.
        if free_for > 12:
            break
    else:
        free_for = 0
    hold(A, frames=3)
    wait_polls(27)
    if i % 3 == 0:
        capture(f"mira_{n:03d}")
        if os.environ.get("ARES_WINDOW_SHOTS"):
            # gdb has ares halted here, so the window holds still. Spectacle takes whichever window is active.
            subprocess.run(["spectacle", "-b", "-n", "-a", "-o", f"{ROOT}/build/shots/ares/mira_{n:03d}.png"], check=True, timeout=30)
        n += 1
print(f"AT end: flags={read32(FLAGS):08x} free={free()}", flush=True)
check(read32(FLAGS) & 0x20000000 != 0, "MIRA_ROAD_SCENE is set")
check(not faults, "no CPU faults")
check(not any(row["problems"] for row in checked), "no display list problems")
finish()
