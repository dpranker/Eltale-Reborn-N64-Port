# Gets from power-on to free movement in the monastery with a new game. Sourced by the Phase 3 scripts.
import math
gdb.execute("source tests/gdb/drive.py")

GAME_STATE = 0x8007B2E4
PLAYER = 0x8007BACC
SPRINT_BIT = 0x0040


def position():
    return read_float(PLAYER), read_float(PLAYER + 8)


def new_game():
    connect()
    gdb.execute(f"hbreak *{POLL_ENTRY:#x}", to_string=True)
    resume()
    gdb.execute("delete", to_string=True)
    wait_polls(120); press(START); wait_polls(120); press(START); wait_polls(120); press(A); wait_polls(60)
    press(START); wait_polls(60); press(A); wait_polls(60); press(A); wait_polls(120); press(A); wait_polls(240)
    for _ in range(60):
        press(A, frames=3, after=25)
        if read32(GAME_STATE) == 0:
            wait_polls(30)
            if read32(GAME_STATE) == 0:
                return
    raise gdb.GdbError("the opening didn't reach free movement")


def speed(stick, buttons=0, frames=30):
    """Walks with the stick held and returns distance per poll, skipping the start of the walk."""
    write32(BUTTONS, buttons)
    write32(STICK, ((stick[0] & 0xFF) << 8) | (stick[1] & 0xFF))
    wait_polls(10)
    x0, z0 = position()
    wait_polls(frames)
    x1, z1 = position()
    write32(BUTTONS, 0)
    write32(STICK, 0)
    wait_polls(10)
    return math.hypot(x1 - x0, z1 - z0) / frames


# From the Dreamcast port's runtime/src/test.c.
PLAYER_STATE = 0x8007BAB8
WARP_TIMER, WARP_FADE_TYPE, WARP_MAP, WARP_ROOM, WARP_ENTRY = 0x8007B2EC, 0x8007B2F0, 0x80085368, 0x8008536C, 0x80085370
ENTRY_MODE, NEXT_MAP, NEXT_ROOM = 0x8007BA4C, 0x80084EE4, 0x80084EE8
BATTLE_STATE, ENCOUNTER_ZONES, ENCOUNTER_SITE, ALLOW_BATTLES = 0x8008C592, 0x8008C560, 0x8008C564, 0x80084F10
ENCOUNTER_DIST, ENCOUNTER_DANGER, RAND_SEED = 0x8008C574, 0x8008C578, 0x8004D748
ENCOUNTER_STEP = 0x8007BA5C
EXP = 0x8007BA68


def write16(addr, value):
    inferior.write_memory(addr, (value & 0xFFFF).to_bytes(2, "big"))


def write_float(addr, value):
    import struct
    inferior.write_memory(addr, struct.pack(">f", value))


def read_s16(addr):
    value = read16(addr)
    return value - 0x10000 if value & 0x8000 else value


def free():
    return read16(PLAYER_STATE) < 3 and read32(GAME_STATE) & 0xDF == 0


def warp(map_id, room=0, entry=0):
    write32(WARP_MAP, map_id)
    write32(WARP_ROOM, room)
    write32(WARP_ENTRY, entry)
    write32(ENTRY_MODE, 0)
    write16(WARP_FADE_TYPE, 0)
    write16(WARP_FADE_TYPE + 2, 0xFFFF)
    write32(WARP_TIMER, 1)
    write32(GAME_STATE, (read32(GAME_STATE) & ~2) | 0x80)
    for _ in range(100):
        wait_polls(10)
        if read32(NEXT_MAP) == map_id and read32(NEXT_ROOM) == room and free():
            wait_polls(30)
            return
    raise gdb.GdbError(f"the warp to map {map_id} didn't finish")


def to_battle_point():
    """Puts Brian 70 units from a battle point, inside an encounter zone, as the game needs for a battle."""
    table, site = read32(ENCOUNTER_ZONES), read32(ENCOUNTER_SITE)
    if not read16(ALLOW_BATTLES) & 1 or table < 0x80000000 or site < 0x80000000:
        raise gdb.GdbError("no random battles here")
    zones, zone_count = read32(table), read32(table + 4)
    points, point_count = read32(site + 8), read32(site + 12)
    for p in range(min(point_count, 256)):
        px, pz = read_s16(points + p * 4), read_s16(points + p * 4 + 2)
        for d in range(8):
            bx, bz = px + 70 * math.cos(d * 0.785398), pz + 70 * math.sin(d * 0.785398)
            for z in range(min(zone_count, 64)):
                e = zones + z * 0x18
                x0, z0, w, h = read_s16(e), read_s16(e + 2), read_s16(e + 4), read_s16(e + 6)
                if x0 + 10 < bx < x0 + w - 10 and z0 + 10 < bz < z0 + h - 10:
                    write_float(PLAYER, bx)
                    write_float(PLAYER + 8, bz)
                    return
    raise gdb.GdbError("no battle point with room for Brian")


def force_battle(seed=0x1234):
    """Every encounter roll succeeds, with the random seed pinned so each ROM gets the same formation."""
    for i in range(300):
        if read16(BATTLE_STATE) & 1:
            return
        write_float(ENCOUNTER_DIST, 50.0)
        write16(ENCOUNTER_DANGER, 2000)
        write32(RAND_SEED, seed)
        hold(stick=(40 if i % 2 else -40, 0), frames=4)
    raise gdb.GdbError("no battle started")


def metric(name, value):
    print(f"METRIC {name} {value}", flush=True)
