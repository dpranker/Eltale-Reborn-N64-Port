# The heaviest display list found so far: Glencoe Forest before Lavaar's ring is cleared, with the spell menu open and
# Healing being cast. Past the game's 2,560 commands, a list writes over the next frame's task and freezes the RSP, as
# Eltale 1.1.2's ring lights did. PC and Dreamcast don't show this, so a new heavy scene would only fail on N64.
gdb.execute("source tests/gdb/dl_common.py")

MAP_GLENCOE_FOREST = 0x20
LAST_COUNT = 0x8004C210            # func_800011DC keeps the size of the last list here, in commands.
LIMIT = 2560
A_BUTTON, C_DOWN, C_LEFT = 0x8000, 4, 2  # Water, then Earth, is Healing.
TOTAL_SPIRITS, STATS = PLAYER_STATE + 0x104, PLAYER_STATE + 0x10
BOX = 0xA0710200                   # tests/mod/combo.c applies writes from inside the game, past the data cache.
B_POKES, B_POKE = BOX + 3 * 4, BOX + 8 * 4
RING_X, RING_Z = -1380, -30
CASTS = 6
# The room's entry point, then spots facing the ring from outside its 200-unit trigger zone.
SPOTS = ((None, None, None, None), (-1170, -30, RING_X, RING_Z), (-1077, -140, RING_X, RING_Z), (-1150, 100, RING_X, RING_Z),
         (-873, 723, RING_X, RING_Z))


def poke(*writes):
    for i, (address, size, value) in enumerate(writes):
        write32(B_POKE + i * 12, address)
        write32(B_POKE + i * 12 + 4, size)
        write32(B_POKE + i * 12 + 8, value)
    write32(B_POKES, len(writes))
    wait_polls(1)


def refill():
    poke((read32(STATS) + 0x24, 4, 0x0A0A0A0A), (TOTAL_SPIRITS, 2, 40), *[(a, 2, 200) for pair in HP_MP for a in pair])


def largest(polls):
    top = 0
    for _ in range(polls // 2):
        wait_polls(2)
        top = max(top, read32(LAST_COUNT))
    return top


title_to_new_game()
talk(6000)
set_flag(16)
clear_scene()
warp(MAP_GLENCOE_FOREST)
wait_polls(120)
refill()
wait_polls(30)
for x, z, fx, fz in SPOTS:
    if x is not None:
        place(x, z, fx, fz)
        wait_polls(30)
    refill()
    idle = largest(30)
    menu = top = 0
    for cast in range(CASTS):
        refill()
        press(C_DOWN, frames=3, after=4)
        menu = max(menu, largest(10))
        press(C_LEFT, frames=3, after=4)
        shot("glencoe_selected")
        press(A_BUTTON, frames=3, after=2)
        top = max(top, largest(40))
    print(f"AT {position()}: idle {idle}, menu {menu}, casting {top}, peak {read32(LIST_PEAK)}", flush=True)

peak = read32(LIST_PEAK)
capture("glencoe_cast")
print(f"RESULT peak {peak} commands, {peak * 100 // LIMIT}% of {LIMIT}", flush=True)
check(peak * 10 <= LIMIT * 9, f"the list stays under 90% of its buffer: {peak} of {LIMIT}")
check(not faults, "no CPU faults")
check(not any(row["problems"] for row in checked), "no display list problems")
finish()
