# Rowan Berry, item 0x1F from Eltale internal 1.3.8: "Wards off curses. Cures weakness, silence and freeze." Its use handler
# works only in battle, on the status block at 0x8007BB34: 0x08 and 0x40 clear at once, and 0x10 clears when the multiplier
# at +0x90 is below 1.0, which it resets to 1.0. Uses the ROM from test-glencoe, for the poke box.
gdb.execute("source tests/gdb/dl_common.py")
import struct

ITEM = 0x1F
INVENTORY = 0x8008CF78
STATUS_POINTER = 0x8007BB34
SILENCE, WEAK, FREEZE = 0x08, 0x10, 0x40
GAME_STATE_BUSY = 0xDF
BOX = 0xA0710200
B_BATTLE, B_POKES, B_POKE = BOX + 5 * 4, BOX + 3 * 4, BOX + 8 * 4


def poke(*writes):
    for i, (address, size, value) in enumerate(writes):
        write32(B_POKE + i * 12, address)
        write32(B_POKE + i * 12 + 4, size)
        write32(B_POKE + i * 12 + 8, value)
    write32(B_POKES, len(writes))
    wait_polls(1)


def berries():
    return sum(1 for b in bytes(inferior.read_memory(INVENTORY, 16)) if b == ITEM)


def status():
    return read16(read32(STATUS_POINTER))


def use_first_item(label):
    press(R, after=40)
    shot(f"rowan_{label}_menu")
    print(f"AT {label} menu: state={read32(GAME_STATE):#x} berries={berries()}", flush=True)
    press(A, after=60)
    shot(f"rowan_{label}_used")
    for _ in range(4):
        if not read32(GAME_STATE) & GAME_STATE_BUSY:
            break
        press(B, after=30)
    wait_polls(30)
    print(f"AT {label} after: state={read32(GAME_STATE):#x} berries={berries()} faults={len(faults)}", flush=True)


title_to_new_game()
talk(6000)
set_flag(16)
clear_scene()
inferior.write_memory(INVENTORY, bytes([ITEM, ITEM, ITEM]))
warp(2)
wait_polls(60)
check(berries() == 3, "three berries in the bag")

use_first_item("field")
check(berries() == 3, f"in the field the berry isn't used up: {berries()}")

clear_scene()
to_battle_point()
wait_polls(5)
force_battle()
wait_polls(60)
check(read32(B_BATTLE) & 1 != 0, "the battle started")
pointer = read32(STATUS_POINTER)
print(f"AT battle: status block {pointer:#x} flags {status():#x}", flush=True)
check(pointer >> 23 == 0x100, f"the status block is in KSEG0 below 8 MB: {pointer:#x}")


def open_battle_menu():
    """R only opens the bag on Brian's turn, so keep trying and keep him alive."""
    for _ in range(40):
        poke(*[(a, 2, 200) for pair in HP_MP for a in pair])
        press(R, after=20)
        if read32(GAME_STATE) & 1:
            return True
        wait_polls(40)
    return False


def cure(flags, left):
    check(open_battle_menu(), "the bag opens on Brian's turn")
    poke((pointer, 2, flags), (pointer + 0x90, 4, struct.unpack(">I", struct.pack(">f", 0.5))[0]))
    wait_polls(5)
    shot(f"rowan_battle_{flags:#x}_menu")
    print(f"AT afflicted: flags {status():#x} berries {berries()}", flush=True)
    press(A, after=5)
    shot(f"rowan_battle_{flags:#x}_used")
    for _ in range(30):
        wait_polls(5)
        if status() & flags == 0 and berries() == left:
            break
    print(f"AT cured: flags {status():#x} multiplier {read_float(pointer + 0x90)} berries {berries()} state {read32(GAME_STATE):#x}", flush=True)
    check(status() & flags == 0, f"status {flags:#x} is gone: {status():#x}")
    if flags & WEAK:
        check(read_float(pointer + 0x90) == 1.0, "the multiplier is back to 1.0")
    check(berries() == left, f"one berry was used: {berries()} left")
    for _ in range(4):
        if not read32(GAME_STATE) & GAME_STATE_BUSY:
            break
        press(B, after=30)
    wait_polls(60)


cure(SILENCE, 2)
cure(WEAK | FREEZE, 1)
check(read32(B_BATTLE) & 1 != 0, "the battle carries on")

check(not faults, "no CPU faults")
finish()
