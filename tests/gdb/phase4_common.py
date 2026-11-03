# Story helpers for the Eltale scripts, after the Dreamcast port's tests/mod_story.txt. Sourced by the Phase 4 scripts.
gdb.execute("source tests/gdb/phase3_common.py")
import json
import os

GAME_MODE = 0x8007B2E0
MODE_FIELD = 1
BUSY_BITS = 0xDF
NPCS, NPC_COUNT, NPC_SIZE = 0x8007BD30, 0x8007BCE4, 0x84
GOLD = 0x8007BA94
ELTALE_SAVE_OFFSET = 0x14C170      # gModSave in 1.1.1, matched from its relocations against the 1.0.0 link map
layout = json.load(open(os.environ.get("ELTALE_LAYOUT", "build/rom/eltale-test/layout.json")))
ELTALE_BASE = next(m["base"] for m in layout["mods"] if m["id"] == "eltale_reborn")
MOD_SAVE = ELTALE_BASE + ELTALE_SAVE_OFFSET
FLAGS = MOD_SAVE + 8


def brian_free():
    return read32(GAME_STATE) & BUSY_BITS == 0 and read16(GAME_MODE) == MODE_FIELD and read16(PLAYER_STATE) <= 2


def talk(max_polls=4000):
    """Presses A through dialogue until Brian has been free for 15 polls. Returns False if he never is."""
    free_since = None
    done = 0
    while done < max_polls:
        if brian_free():
            free_since = done if free_since is None else free_since
            if done - free_since >= 15:
                return True
            wait_polls(5)
            done += 5
        else:
            free_since = None
            hold(A, frames=3)
            wait_polls(18)
            done += 21
    return False


def place(x, z, fx=None, fz=None):
    write_float(PLAYER, x)
    write_float(PLAYER + 8, z)
    if fx is not None:
        write_float(PLAYER + 0x10, math.atan2(fx - x, fz - z))


def set_flag(bit):
    addr = FLAGS + bit // 8
    value = inferior.read_memory(addr, 1).tobytes()[0] | (1 << (bit % 8))
    inferior.write_memory(addr, bytes([value]))


def to_npc(kind, distance):
    for i in range(min(read32(NPC_COUNT), 16)):
        npc = NPCS + i * NPC_SIZE
        definition = read32(npc + 0x80)
        if definition == 0 or read16(definition + 2) != kind:
            continue
        nx, nz, rot = read_float(npc + 0x14), read_float(npc + 0x1C), read_float(npc + 0x24)
        bx, bz = nx + math.sin(rot) * distance, nz + math.cos(rot) * distance
        place(bx, bz, nx, nz)
        return True
    return False


def status(label):
    print(f"AT {label}: map={read32(NEXT_MAP)} room={read32(NEXT_ROOM)} mode={read16(GAME_MODE)} state={read32(GAME_STATE):#x} "
          f"pos=({read_float(PLAYER):.0f},{read_float(PLAYER + 8):.0f}) flags={read32(FLAGS):08x} faults={len(faults)} "
          f"rt_error={read32(layout['runtime_symbols']['rt_error']):#x}", flush=True)


def title_to_new_game():
    connect()
    gdb.execute(f"hbreak *{POLL_ENTRY:#x}", to_string=True)
    resume()
    gdb.execute("delete", to_string=True)
    wait_polls(660)                    # the intro ignores Start for about 20 s
    press(START)
    for _ in range(40):
        wait_polls(10)
        if read16(GAME_MODE) == 3:
            break
    wait_polls(120)
    shot("p4_title")
    press(START)
    wait_polls(120)
    press(A)
    wait_polls(90)
