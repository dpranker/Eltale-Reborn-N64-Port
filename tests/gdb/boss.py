# Finds Solvaring's room, starts the fight the game's own way, by walking into range, and runs it under the fault
# detector and the display list checker. Screenshots go to build/shots/boss_*.
gdb.execute("source tests/gdb/dl_common.py")

BOSS_INDEX, BOSS_ACTOR = 0x8007D1A0, 0x8007D1A8   # func_8000B740 fights when Brian is in range of this actor.
CONNOR_FOREST = 0x1F


def find_boss():
    for room in range(0, 16):
        clear_scene()
        try:
            warp(CONNOR_FOREST, room)
        except gdb.GdbError as error:
            print(f"AT room {room}: {error}", flush=True)
            continue
        index = read32(BOSS_INDEX)
        print(f"AT room {room}: boss={index} battle={read16(BATTLE_STATE)} state={read32(GAME_STATE):#x}", flush=True)
        if index:
            return room
    return None


if TARGET == "eltale":
    title_to_new_game()
    talk(6000)
    set_flag(16)
else:
    new_game()
clear_scene()
room = find_boss()
check(room is not None, "a boss room was found")
if room is None:
    finish()
shot("boss_room")
for addr in (0x8007BA84, 0x8007BA86, 0x8007BA88, 0x8007BA8A):
    write16(addr, 999)


def boss_position():
    return read_float(BOSS_ACTOR + 0x24), read_float(BOSS_ACTOR + 0x2C)


def trace(label):
    print(f"AT {label}: pos={position()} boss={boss_position()} target={read32(0x80086DC0 + 0x80):#x} "
          f"battle={read16(BATTLE_STATE)} state={read32(GAME_STATE):#x} player={read16(PLAYER_STATE):#x}", flush=True)


trace("room")
wait_polls(120)
trace("after standing")
bossx, bossz = boss_position()
bx, bz = position()
for i in range(120):                  # Walk at the boss. The stick is relative to the camera, so aim by trying.
    if read16(BATTLE_STATE) & 1 or read32(GAME_STATE) & 2:
        break
    away = math.hypot(bossx - bx, bossz - bz)
    if i % 6 == 0:
        bx, bz = position()
        away = math.hypot(bossx - bx, bossz - bz)
        step = min(away, 60)
        place(bx + (bossx - bx) / max(away, 1) * step, bz + (bossz - bz) / max(away, 1) * step, bossx, bossz)
        trace(f"step {i} away {away:.0f}")
    wait_polls(5)
trace("in range")
for i in range(80):
    if read16(BATTLE_STATE) & 1:
        break
    hold(A, frames=3)
    wait_polls(15)
    if i % 10 == 0:
        trace(f"intro {i}")
print(f"AT boss intro done: battle={read16(BATTLE_STATE)} state={read32(GAME_STATE):#x} faults={len(faults)}", flush=True)
check(read16(BATTLE_STATE) & 1 != 0, "the boss fight started")
shot("boss_start")
capture("boss_start")
reset()
for i in range(40):
    stay_alive()
    hold(stick=(40 if i % 2 else -40, 20), frames=20)
    hold(A, frames=3)
    wait_polls(12)
    if i % 10 == 9:
        capture(f"boss_{i}")
report("boss_fight")
shot("boss_mid")
metric("enemy_hp_before_finish", read16(0x8007C998 + 0xA))
for i in range(120):
    if not read16(BATTLE_STATE) & 1:
        break
    stay_alive()
    write16(0x8007C998 + 0xA, 1)
    ex, ez = read_float(0x8007C998 + 0x24), read_float(0x8007C998 + 0x2C)
    bx, bz = position()
    away = math.hypot(bx - ex, bz - ez)
    if away > 25:
        place(ex + (bx - ex) / away * 20, ez + (bz - ez) / away * 20, ex, ez)
    hold(A, frames=3)
    wait_polls(25)
won = not read16(BATTLE_STATE) & 1
check(won, "the boss was beaten")
shot("boss_end")
ok = talk(3600) if TARGET == "eltale" else True
check(ok, "the victory scene finishes")
shot("boss_after")
print(f"AT after the boss: state={read32(GAME_STATE):#x}", flush=True)
report_stacks()
check(not faults, "no CPU faults")
check(not any(row["problems"] for row in checked), "no display list problems")
finish()
