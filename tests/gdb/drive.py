# Helpers for gdb scripts that play the game through the test_input mod (tests/mod/input.c). Sourced by gdb.
import gdb
import os
import subprocess
import time

MAILBOX = 0xA0710000
BUTTONS, STICK, POLLS = MAILBOX, MAILBOX + 4, MAILBOX + 8
A, B, Z, START, DUP, DDOWN, DLEFT, DRIGHT = 0x8000, 0x4000, 0x2000, 0x1000, 0x0800, 0x0400, 0x0200, 0x0100
L, R, CUP, CDOWN, CLEFT, CRIGHT = 0x0020, 0x0010, 0x0008, 0x0004, 0x0002, 0x0001
FAULT_KIND = MAILBOX + 12
EXPECT_FAULTS = False
POLL_ENTRY = 0x8003AC9C  # osContGetReadData
ROOT = os.getcwd()
inferior = None
failures = 0
faults = []
fault_registers = []
IGNORED_SIGNALS = ("SIGTRAP", "SIGINT", "SIGWINCH", "0")


def on_stop(event):
    """ares reports CPU exceptions as signals. The game has no fault handler, so one means a thread just died."""
    if isinstance(event, gdb.SignalEvent) and event.stop_signal not in IGNORED_SIGNALS:
        pc = int(gdb.parse_and_eval("$pc")) & 0xFFFFFFFF
        faults.append((event.stop_signal, pc))
        print(f"FAULT: {event.stop_signal} at {pc:#x}", flush=True)
        fault_registers.append(gdb.execute("info registers", to_string=True))


def connect():
    global inferior
    port = int(gdb.parse_and_eval("$port"))
    for line in ("set pagination off", "set confirm off", "set width 0", "set architecture mips:4300", "set endian big"):
        gdb.execute(line)
    gdb.execute(f"target remote 127.0.0.1:{port}", to_string=True)
    inferior = gdb.selected_inferior()
    gdb.events.stop.connect(on_stop)


def read32(addr):
    return int.from_bytes(inferior.read_memory(addr, 4).tobytes(), "big")


def read16(addr):
    return int.from_bytes(inferior.read_memory(addr, 2).tobytes(), "big")


def read_float(addr):
    import struct
    return struct.unpack(">f", inferior.read_memory(addr, 4).tobytes())[0]


def write32(addr, value):
    inferior.write_memory(addr, (value & 0xFFFFFFFF).to_bytes(4, "big"))


def resume():
    gdb.execute("continue", to_string=True)
    if faults and not EXPECT_FAULTS:
        print(f"FAULT: {faults[-1][0]} at {faults[-1][1]:#x}\n{fault_registers[-1]}", flush=True)
        raise gdb.GdbError(f"CPU fault: {faults[-1][0]} at {faults[-1][1]:#x}")


def wait_polls(count):
    """Runs the game for `count` controller polls, about one per game frame."""
    target = read32(POLLS) + count
    gdb.execute(f"hbreak *{POLL_ENTRY:#x} if {{int}}{POLLS:#x} >= {target}", to_string=True)
    resume()
    gdb.execute("delete", to_string=True)


# Modern Gameplay 1.5.4's "Hold A to pass": with no enemy in reach, A has to be held a second to pass the turn. Held this
# long, A passes or swings the way a tap did before.
PASS_POLLS = 75


def hold(buttons=0, stick=None, frames=1):
    write32(BUTTONS, buttons)
    write32(STICK, 0 if stick is None else ((stick[0] & 0xFF) << 8) | (stick[1] & 0xFF))
    wait_polls(frames)
    write32(BUTTONS, 0)
    write32(STICK, 0)


def press(buttons, frames=3, after=12):
    hold(buttons, frames=frames)
    wait_polls(after)


def shot(name):
    """Saves what VI is showing to build/shots/<name>.png."""
    origin = read32(0xA4400004) & 0xFFFFFF
    width = read32(0xA4400008) & 0xFFF
    os.makedirs(f"{ROOT}/build/shots", exist_ok=True)
    raw = f"{ROOT}/build/shots/{name}.bin"
    gdb.execute(f"dump binary memory {raw} {0xA0000000 + origin:#x} {0xA0000000 + origin + width * 240 * 2:#x}", to_string=True)
    subprocess.run(["python3", f"{ROOT}/tools/fb_png.py", raw, str(width), f"{ROOT}/build/shots/{name}.png"], check=True)
    os.remove(raw)


def check(ok, text):
    global failures
    print(("ok: " if ok else "FAIL: ") + text, flush=True)
    if not ok:
        failures += 1


def finish():
    gdb.execute("detach", to_string=True)
    gdb.execute(f"quit {1 if failures else 0}")
