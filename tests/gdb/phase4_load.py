# From a fresh boot, loads the save tests/gdb/phase4_story.py made, and checks Eltale's flags came back. The mod
# keeps them in bytes 0x160-0x1FF of the save, so this round-trips them through the real Controller Pak code.
gdb.execute("source tests/gdb/phase4_common.py")
SAVED_FLAGS = 0x63011900
connect()
gdb.execute(f"hbreak *{POLL_ENTRY:#x}", to_string=True)
resume()
gdb.execute("delete", to_string=True)
check(read32(FLAGS) == 0, "the flags start clear on a fresh boot")
wait_polls(660)
press(START)
for _ in range(40):
    wait_polls(10)
    if read16(GAME_MODE) == 3:
        break
wait_polls(120)
press(START)
wait_polls(120)
check(read32(FLAGS) == 0, "the flags are clear at the title")
hold(stick=(70, 0), frames=9)      # NEW -> LOAD
wait_polls(25)
press(A, after=90)
shot("p4_load_slots"); status("load slots")
press(A, after=60)
shot("p4_load_confirm")
press(A, after=180)
shot("p4_loaded"); status("loaded")
check(read32(FLAGS) == SAVED_FLAGS, f"the story flags came back: {read32(FLAGS):08x}")
check(read32(NEXT_MAP) == 15, "the save loads at the Melrode Inn")
check(not faults, "no CPU faults")
metric("cpu_faults", len(faults))
finish()
