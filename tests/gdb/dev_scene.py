# Runs one of the mod's dev_scene jumps, pressing A through it, with fault detection and periodic display list checks.
gdb.execute("source tests/gdb/dl_common.py")
NAME = os.environ["DEV_SCENE_NAME"]
POLLS_TO_RUN = int(os.environ.get("DEV_SCENE_POLLS", "6000"))

title_to_new_game()
set_flag(8)                        # FLAG_PROLOGUE_DONE: Brian is free in the monastery, and dev mode jumps from there.
wait_polls(120)
for addr in (0x8007BA84, 0x8007BA86, 0x8007BA88, 0x8007BA8A):
    write16(addr, 999)
done = 0
last_shot = -1000
while done < POLLS_TO_RUN:
    stay_alive()
    hold(A, frames=3)
    wait_polls(27)
    done += 30
    if done - last_shot >= 600:
        last_shot = done
        capture(f"{NAME}_{done:05d}")
        print(f"AT {done}: mode={read16(GAME_MODE)} state={read32(GAME_STATE):#x} map={read32(NEXT_MAP)} room={read32(NEXT_ROOM)} "
              f"battle={read16(BATTLE_STATE)} flags={read32(FLAGS):08x}", flush=True)
report_stacks()
check(not faults, f"{NAME}: no CPU faults")
check(not any(row["problems"] for row in checked), f"{NAME}: no display list problems")
finish()
