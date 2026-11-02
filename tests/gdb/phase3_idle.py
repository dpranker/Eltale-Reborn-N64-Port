# Leaves the game alone in the field until the runner's timeout interrupts it, then checks it's still alive.
# A crash stops the controller polls and retraces, so the counts show it.
gdb.execute("source tests/gdb/phase3_common.py")
new_game()
warp(2)
polls_before = read32(POLLS)
shot("p3_idle_start")
print("idling", flush=True)
gdb.execute("continue", to_string=True)   # returns when run_ares.sh's timeout sends SIGINT
polls = read32(POLLS) - polls_before
metric("idle_polls", polls)
metric("idle_game_state", read32(GAME_STATE))
metric("idle_map", read32(NEXT_MAP))
metric("idle_battle", read16(BATTLE_STATE))
first = read32(0xA4400010)
wait_polls(30)
metric("idle_alive_after", read32(POLLS) - polls_before - polls)
shot("p3_idle_end")
report_stacks()
metric("cpu_faults", len(faults))
finish()
