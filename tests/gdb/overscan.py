# Walks the screens with 2D UI and reports every rectangle in the 8-pixel margins or cut by the scissor, with a screenshot of each.
gdb.execute("source tests/gdb/dl_common.py")
INVENTORY = 0x8008CF78


def screen(name):
    row = capture(name)
    print(f"AT {name}: mode={read16(GAME_MODE)} state={read32(GAME_STATE):#x} edge={len(row['edge_rects'])}", flush=True)


title_to_new_game()
screen("new_game")
talk(6000)
set_flag(16)
clear_scene()
inferior.write_memory(INVENTORY, bytes([0, 1, 2, 3, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E]))
inferior.write_memory(GOLD, (1234).to_bytes(4, "big"))
warp(2)
wait_polls(60)
screen("field")
press(START, after=40)
screen("start_menu")
for page in range(4):
    press(R, after=40)
    screen(f"start_menu_{page}")
while read16(GAME_MODE) != 1:
    press(B, after=30)
clear_scene()
press(R, after=40)
print(f"AT item menu: state={read32(GAME_STATE):#x}", flush=True)
screen("item_menu")
press(R, after=40)
clear_scene()
to_battle_point()
wait_polls(5)
force_battle()
wait_polls(60)
screen("battle")
report_stacks()
check(not faults, "no CPU faults")
check(not any(row["problems"] for row in checked), "no display list problems")
for row in checked:
    cut = [e["rect"] for e in row["edge_rects"] if e["clipped"]]
    check(not cut, f"{row['scene']}: no 2D rectangle cut by the scissor {cut}")
    near = [e["rect"] for e in row["edge_rects"] if not e["clipped"]]
    if near:
        print(f"NEAR {row['scene']}: {near}", flush=True)
finish()
