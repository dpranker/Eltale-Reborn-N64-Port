# Warps to every room of every map and reports its heaviest display list, standing and with the spell menu open, using
# the game's own peak count, reset from inside the game for each room. Lists how close each room comes to the limit.
gdb.execute("source tests/gdb/dl_common.py")

MAP_TABLE, MAP_ENTRY_SIZE, MAP_COUNT = 0x80054F10, 0x44, 0x24
LIMIT = 2560                       # Past this, a list writes over the next frame's task. See tests/gdb/glencoe.py.
C_DOWN, B_BUTTON = 4, 0x4000
BOX = 0xA0710200                   # tests/mod/combo.c applies writes from inside the game, past the data cache.
B_POKES, B_POKE = BOX + 3 * 4, BOX + 8 * 4
SCENE_POLLS = 90


def reset_peak():
    write32(B_POKE, LIST_PEAK)
    write32(B_POKE + 4, 4)
    write32(B_POKE + 8, 0)
    write32(B_POKES, 1)
    wait_polls(2)


def room_count(map_id):
    return read32(MAP_TABLE + map_id * MAP_ENTRY_SIZE + 0x40)


def visit(map_id, room):
    """Warps, pressing A through any scene that starts or was left running. False if the room never settles."""
    write32(WARP_MAP, map_id)
    write32(WARP_ROOM, room)
    write32(WARP_ENTRY, 0)
    write32(ENTRY_MODE, 0)
    write16(WARP_FADE_TYPE, 0)
    write16(WARP_FADE_TYPE + 2, 0xFFFF)
    write32(WARP_TIMER, 1)
    write32(GAME_STATE, (read32(GAME_STATE) & ~2) | 0x80)
    for _ in range(40):
        wait_polls(15)
        if read32(NEXT_MAP) == map_id and read32(NEXT_ROOM) == room and free():
            wait_polls(30)
            return True
        hold(A, frames=2)
    return False


title_to_new_game()
talk(6000)
set_flag(16)
clear_scene()
rows, skipped = [], []
for map_id in range(MAP_COUNT):
    for room in range(room_count(map_id)):
        if not visit(map_id, room):
            skipped.append((map_id, room))
            print(f"SKIP map {map_id:#04x} room {room}", flush=True)
            continue
        reset_peak()
        wait_polls(SCENE_POLLS)
        idle = read32(LIST_PEAK)
        press(C_DOWN, frames=3, after=30)
        menu = read32(LIST_PEAK)
        press(B_BUTTON, frames=3, after=10)
        rows.append((max(idle, menu), idle, map_id, room))
        print(f"ROOM {map_id:#04x} {room}: idle {idle} menu {menu} ({menu * 100 // LIMIT}%)", flush=True)
        if menu * 10 > LIMIT * 7:
            shot(f"sweep_heavy_{map_id:02x}_{room}")

rows.sort(reverse=True)
print("RESULT rooms", len(rows), "skipped", skipped, flush=True)
print("RESULT heaviest", rows[:12], flush=True)
check(rows and rows[0][0] * 10 <= LIMIT * 9, f"every room stays under 90% of the buffer: {rows[0][0]} of {LIMIT}")
check(not faults, "no CPU faults")
finish()
