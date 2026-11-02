# Frame-time helpers for any ROM with the test_perf mod. PERF_TARGET says which ROM it is.
# Percentages are of a 30 fps frame: two retraces, measured in Count on the same run. See tests/mod/perf.c.
import json
import os

gdb.execute("source tests/gdb/phase3_common.py")
TARGET = os.environ["PERF_TARGET"]
if TARGET == "eltale":
    gdb.execute("source tests/gdb/phase4_common.py")

PERF = 0xA0710100
P_FRAMES, P_RETRACES, P_COUNT, P_GAME_SUM, P_GAME_MAX, P_RCP_SUM, P_RCP_MAX = 1, 2, 3, 4, 5, 6, 7
P_WRITEBACK_SUM, P_WRITEBACK_MAX, P_WRITEBACKS, P_HIST = 8, 9, 10, 11
DISPLAY_LIST_PEAK = 0x8007B34C     # func_800011DC keeps the most commands it has built in one frame
NPCS, NPC_COUNT, NPC_SIZE = 0x8007BD30, 0x8007BCE4, 0x84
HP_MP = ((0x8007BA84, 0x8007BA86), (0x8007BA88, 0x8007BA8A))


def place(x, z, fx, fz):
    write_float(PLAYER, x)
    write_float(PLAYER + 8, z)
    write_float(PLAYER + 0x10, math.atan2(fx - x, fz - z))


def word(i):
    return read32(PERF + i * 4)


def reset():
    write32(PERF, 1)
    wait_polls(3)


def report(name):
    frames, retraces, count = word(P_FRAMES), word(P_RETRACES), word(P_COUNT)
    if not frames or not retraces:
        raise gdb.GdbError(f"{name}: no frames measured")
    budget = count / retraces * 2 / 100
    hist = [word(P_HIST + i) for i in range(8)]
    row = {
        "scene": name,
        "frames": frames,
        "fps": frames * 59.94 / retraces,
        "worst": max(i for i, n in enumerate(hist) if n),
        "hist": hist,
        "game": word(P_GAME_SUM) / frames / budget,
        "game_peak": word(P_GAME_MAX) / budget,
        "rcp": word(P_RCP_SUM) / frames / budget,
        "rcp_peak": word(P_RCP_MAX) / budget,
        "writeback": word(P_WRITEBACK_SUM) / max(word(P_WRITEBACKS), 1) / budget,
        "writeback_peak": word(P_WRITEBACK_MAX) / budget,
        "count_per_retrace": count / retraces,
        "commands": read32(DISPLAY_LIST_PEAK),
        "people": read32(NPC_COUNT),
        "faults": len(faults),
    }
    print("SCENE " + json.dumps(row), flush=True)
    shot(f"perf_{TARGET}_{name}")


def stay_alive():
    for now, most in HP_MP:
        write16(now, read16(most))


def clear_scene():
    """A teleport can start a scene. Presses A through it, so the next warp starts from free movement."""
    for _ in range(200):
        if free():
            return
        hold(A, frames=3)
        wait_polls(18)
    raise gdb.GdbError("a scene didn't finish")


def measure(name, frames=300):
    reset()
    wait_polls(frames)
    report(name)


def walk_back_and_forth(name, seconds=5):
    """As the Dreamcast port's tests/perf.txt: up the street and back."""
    room = read32(NEXT_ROOM)
    reset()
    hold(stick=(0, 70), frames=seconds * 30)
    hold(stick=(0, -70), frames=seconds * 30)
    check(read32(NEXT_ROOM) == room, f"{name} stayed in its room")
    report(name)


def melrode_street():
    clear_scene()
    try:
        warp(0)
    except gdb.GdbError:           # Eltale can start a scene on arrival, which holds the warp's wait for free movement.
        clear_scene()
        if read32(NEXT_MAP) != 0 or read32(NEXT_ROOM) != 0:
            raise
    wait_polls(60)


def melrode_crowd():
    """Stands beside each person on the street, looking at them. The crowd is the heavy part, and Eltale adds to it."""
    people = []
    for i in range(min(read32(NPC_COUNT), 32)):
        npc = NPCS + i * NPC_SIZE
        definition = read32(npc + 0x80)
        if definition:
            people.append((read16(definition + 2), read_float(npc + 0x14), read_float(npc + 0x1C)))
    seen = {}
    for kind, nx, nz in people:
        seen[kind] = seen.get(kind, 0) + 1
        place(nx + 30, nz + 30, nx, nz)
        wait_polls(10)
        if read32(NEXT_ROOM) != 0 or read32(NEXT_MAP) != 0:
            print(f"SKIP person {kind}_{seen[kind]}: left the street", flush=True)
            melrode_street()
            continue
        reset()
        wait_polls(45)
        if free():
            report(f"melrode_person_{kind}_{seen[kind]}")
        else:
            print(f"SKIP person {kind}_{seen[kind]}: a scene started", flush=True)
        clear_scene()
    return len(people)


