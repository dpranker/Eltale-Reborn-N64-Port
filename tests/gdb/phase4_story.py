# New game through the prologue, a sign, the farewell, Mira on the road, Odran on the Holy Plain and a save at the
# inn. Follows the Dreamcast port's tests/mod_story.txt. Screenshots go to build/shots/p4_*.
gdb.execute("source tests/gdb/phase4_common.py")
title_to_new_game()
shot("p4_prologue_1"); status("prologue start")
ok = talk(6000)
shot("p4_prologue_end"); status(f"prologue end, finished={ok}")
check(ok, "the prologue finishes")
check(read32(FLAGS) & 0x00010000 != 0, "the mod set PROLOGUE_DONE")

set_flag(16)                 # skip the monastery goodbyes
write32(GOLD, 500)
warp(0)                      # Melrode
wait_polls(45)
shot("p4_town"); status("Melrode")
place(175, -37, 175, -43)    # under the inn sign
wait_polls(10)
press(A, after=45)
shot("p4_sign"); status("sign")
talk(600)

place(12, 590, 12, 645)      # the road out: the village sees Brian off, then Mira catches him up
wait_polls(75)
shot("p4_farewell_1"); status("farewell")
press(A, after=20); press(A, after=20)
shot("p4_farewell_2")
ok = talk(3600)
shot("p4_farewell_end"); status(f"farewell end, finished={ok}")
place(12, 595, 12, 645)
wait_polls(75)
shot("p4_mira_1"); status("Mira")
ok = talk(3600)
shot("p4_mira_end"); status(f"Mira end, finished={ok}")

warp(2)                      # the Holy Plain
wait_polls(30)
place(70, 60, 70, 40)        # Odran's zone
wait_polls(90)
shot("p4_odran_1"); status("Odran")
ok = talk(3600)
shot("p4_odran_end"); status(f"Odran end, finished={ok}")

warp(0x0F, 5, 0)             # Melrode Inn, ground floor
wait_polls(30)
found = to_npc(6, 18)        # across the counter from Agnes
check(found, "the innkeeper is here")
wait_polls(15)
press(A, after=45); shot("p4_inn_1")
press(A, after=45); shot("p4_inn_2")
press(A, after=90); shot("p4_save_1"); status("save menu")
press(A, after=75); shot("p4_save_2")
press(A, after=75); shot("p4_save_3"); status("after save")
hold(stick=(0, -70), frames=9)    # "Continue save?" No
wait_polls(15)
press(A, after=90); shot("p4_save_4")
report_stacks()
check(not faults, "no CPU faults")
metric("cpu_faults", len(faults))
finish()
