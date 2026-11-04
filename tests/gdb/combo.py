# Timed second swings and back attacks in a real battle, on the staff code in Eltale's src/staff_combo.c, watched and
# steered by tests/mod/combo.c. The seed is pinned at each hit roll, so swings compare exactly, and the enemy's facing
# is set there, since the back attack reads it straight after. COMBO_OFF=1 is a ROM with both options off.
gdb.execute("source tests/gdb/dl_common.py")
import struct

OPTIONS_ON = not os.environ.get("COMBO_OFF")
ACTOR = PLAYER_STATE
TOTAL_SPIRITS, STATS = ACTOR + 0x104, ACTOR + 0x10
ENEMY0, ENEMY_SIZE = 0x8007C998, 0x128
BOX = 0xA0710200
B_SEED, B_FACING, B_PRESS_AT, B_POKES, B_STATE, B_BATTLE, B_LOGS = (BOX + i * 4 for i in range(7))
B_HP = BOX + 7 * 4
B_POKE, B_LOG = BOX + 8 * 4, BOX + 72 * 4
NONE = 0xFFFFFFFF
EV_ROLL, EV_HIT, EV_MISS, EV_BACKHAND, EV_PRESS, EV_HP = 1, 2, 3, 4, 5, 6
STATE_SWING = 13


def enemy_hp(slot):
    return ENEMY0 + slot * ENEMY_SIZE + 0xA


def in_battle():
    return read32(B_BATTLE) & 1 != 0


def state():
    return read32(B_STATE)


def poke(*writes):
    """Applies (address, size, value) writes from inside the game at the next poll."""
    for i, (address, size, value) in enumerate(writes):
        write32(B_POKE + i * 12, address)
        write32(B_POKE + i * 12 + 4, size)
        write32(B_POKE + i * 12 + 8, value)
    write32(B_POKES, len(writes))
    wait_polls(1)


def float_bits(value):
    return struct.unpack(">I", struct.pack(">f", value))[0]


def start_swing(each):
    """Stands Brian beside the first enemy on his turn and presses A until the swing starts."""
    stats = read32(STATS)
    for _ in range(150):
        if not in_battle():
            raise gdb.GdbError("the battle ended early")
        ex, ez = read_float(ENEMY0 + 0x24), read_float(ENEMY0 + 0x2C)
        bx, bz = position()
        away = max(math.hypot(bx - ex, bz - ez), 1)
        x, z = ex + (bx - ex) / away * 20, ez + (bz - ez) / away * 20
        poke(*[(a, 2, 999) for pair in HP_MP for a in pair],
             (stats + 0x24, 4, each * 0x01010101), (TOTAL_SPIRITS, 2, each * 4),
             (PLAYER, 4, float_bits(x)), (PLAYER + 8, 4, float_bits(z)), (PLAYER + 0x10, 4, float_bits(math.atan2(ex - x, ez - z))))
        write32(BUTTONS, A)
        wait_polls(1)
        write32(BUTTONS, 0)
        for _ in range(12):
            if state() == STATE_SWING:
                return
            wait_polls(1)
    raise gdb.GdbError("Brian never swung")


def swing(each=10, press_at=None, facing=None, seed=0x1234, hp=9000, capture_as=None):   # 9000 survives any test hit.
    """One swing through to its end. Returns what the probe saw."""
    write32(B_LOGS, 0)
    write32(B_SEED, seed)
    write32(B_FACING, NONE if facing is None else float_bits(facing))
    write32(B_PRESS_AT, NONE if press_at is None else press_at)
    write32(B_HP, hp)
    start_swing(each)
    captured = False
    for _ in range(80):
        if state() != STATE_SWING:
            break
        wait_polls(1)
        if capture_as and not captured and any(read32(B_LOG + i * 4) >> 24 == EV_BACKHAND for i in range(read32(B_LOGS))):
            captured = True
            capture(capture_as)
    write32(B_PRESS_AT, NONE)
    write32(BUTTONS, 0)
    events = [read32(B_LOG + i * 4) for i in range(read32(B_LOGS))]
    out = dict(
        rolls=sum(1 for e in events if e >> 24 == EV_ROLL),
        hits=[e & 0xFFFFFF for e in events if e >> 24 == EV_HIT],
        hp=[e & 0xFFFFFF for e in events if e >> 24 == EV_HP],
        misses=sum(1 for e in events if e >> 24 == EV_MISS),
        backhands=sum(1 for e in events if e >> 24 == EV_BACKHAND),
        seen=[e & 0xFFFFFF for e in events if e >> 24 == EV_PRESS and e & 0xFFFFFF < 19],   # The A that started it is still seen at 19.
        slots=[e & 0xFFFFFF for e in events if e >> 24 == EV_ROLL],
    )
    print(f"AT swing each={each} press_at={press_at} facing={None if facing is None else round(math.degrees(facing))} "
          f"seed={seed:#x}: {out} state={state()} faults={len(faults)}", flush=True)
    return out


title_to_new_game()
talk(6000)
set_flag(16)
clear_scene()
warp(2)
to_battle_point()
wait_polls(5)
force_battle()
wait_polls(60)
check(in_battle(), "the battle started")
print(f"AT battle: attack={read16(ACTOR + 0x10A)} enemy_hp={read16(ENEMY0 + 0xA)}", flush=True)

# A seed that hits, for everything that compares power, and one that misses if there is one.
HIT_SEED = MISS_SEED = None
for seed in range(0x1000, 0x1000 + 32 * 0x111, 0x111):
    result = swing(seed=seed)
    if result["hits"] and HIT_SEED is None:
        HIT_SEED, base = seed, result["hits"][0]
        check(result["hp"] and result["hp"][0] < 9000, f"the hit took HP off the enemy: {result['hp']}")
    if result["misses"] and MISS_SEED is None:
        MISS_SEED = seed
    if HIT_SEED is not None and MISS_SEED is not None:
        break
check(HIT_SEED is not None, "a swing landed")
metric("base_power", base)
second = base >> 1

# The timing window: 10 spirits in each element is 40 spread evenly, 5 frames.
result = swing(seed=HIT_SEED)
check(result["hits"] == [base] and not result["backhands"] and not result["seen"], "no press: one hit")
result = swing(press_at=6, seed=HIT_SEED)
check(result["seen"] == [6], f"a press reached the handler at frame 6: {result['seen']}")
check(result["hits"] == [base] and not result["backhands"], "a press one frame before the 5-frame window does nothing")
result = swing(press_at=5, seed=HIT_SEED, capture_as="combo_backhand" if OPTIONS_ON else None)
check(result["seen"] == [5], f"a press reached the handler at frame 5: {result['seen']}")
if OPTIONS_ON:
    check(result["backhands"] == 1 and result["hits"] == [base, second], f"first frame of the window: backhand at half power {result['hits']}")
    check(len(result["hp"]) == 2 and min(result["hp"]) > 8000, f"both hits landed on the enemy: {result['hp']}")
else:
    check(not result["backhands"] and result["hits"] == [base], "option off: a press in the window does nothing")
result = swing(press_at=1, seed=HIT_SEED)
check(result["seen"] == [1], f"a press reached the handler at frame 1: {result['seen']}")
if OPTIONS_ON:
    check(result["backhands"] == 1 and result["hits"] == [base, second], "last frame of the window: backhand")

# One spirit in each element is a single frame.
result = swing(each=1, press_at=2, seed=HIT_SEED)
check(not result["backhands"], "one spirit each: frame 2 is too early")
result = swing(each=1, press_at=1, seed=HIT_SEED)
if OPTIONS_ON:
    check(result["backhands"] == 1, "one spirit each: frame 1 works")

# Back attacks.
front = swing(facing=0.0, seed=HIT_SEED)["hits"][0]
side = swing(facing=math.radians(130), seed=HIT_SEED)["hits"][0]
behind = swing(facing=math.radians(140), seed=HIT_SEED)["hits"][0]
back = swing(facing=math.pi, seed=HIT_SEED)["hits"][0]
other = swing(facing=-math.pi, seed=HIT_SEED)["hits"][0]
bonus = front + (front >> 1) if OPTIONS_ON else front
check(front == base, f"from the front: normal power ({front}, base {base})")
check(side == base, f"130 degrees off: normal power ({side})")
check(behind == bonus, f"140 degrees off: {behind}, expected {bonus}")
check(back == bonus and other == bonus, f"directly behind, both ways round: {back} and {other}, expected {bonus}")
if OPTIONS_ON:
    both = swing(press_at=3, facing=math.pi, seed=HIT_SEED)
    half = second + (second >> 1)
    check(both["hits"] == [bonus, half], f"backhand from behind: {both['hits']}, expected {[bonus, half]}")

# Reported, not judged: staff_combo.c's comment says the first hit must land, its code doesn't check.
if MISS_SEED is not None:
    result = swing(press_at=3, seed=MISS_SEED)
    print(f"RESULT press after a miss: rolls={result['rolls']} misses={result['misses']} backhands={result['backhands']}", flush=True)
else:
    print("RESULT press after a miss: no seed missed", flush=True)

# Weak swings on the enemy's real HP: the first hit's damage must still be there for the second.
if OPTIONS_ON:
    result = swing(each=1, press_at=1, facing=0.0, seed=HIT_SEED, hp=0)
    check(len(result["hp"]) == 2 and result["hp"][1] < result["hp"][0], f"the backhand adds to the first hit's damage: {result['hp']}")

# A first hit that kills: the queued backhand must not run, and the battle must end cleanly.
result = swing(press_at=3, seed=HIT_SEED, hp=1)
check(not result["backhands"] and len(result["hits"]) == 1, f"no backhand on a dead enemy: {result}")
for _ in range(120):
    if not in_battle():
        break
    poke(*[(enemy_hp(slot), 2, 0) for slot in range(4)], *[(a, 2, 999) for pair in HP_MP for a in pair])
    hold(A, frames=3)
    wait_polls(20)
check(not in_battle(), "the battle ended")
report_stacks()
check(not faults, "no CPU faults")
check(not any(row["problems"] for row in checked), "no display list problems")
finish()
