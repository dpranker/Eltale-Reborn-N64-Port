# Captures a whole frame's display lists at the moment the RSP would read them, and checks them with tools/dl_check.py.
gdb.execute("source tests/gdb/perf_common.py")
import sys
sys.path.insert(0, "tools")
import dl_check

TASK_START = 0x80034694            # osSpTaskStartGo, after the runtime's cache writeback in osSpTaskLoad's hook
SWAP_FLAG = 0x40                   # The scheduler's task flag: this task ends the frame.
M_GFXTASK = 1
LIST_PEAK = 0x8007B34C             # The game's own count of the most commands any frame's list has used since boot.
BLOCK = 0x10000
checked = []


def read_rdram(blocks):
    def read(address, size):
        out = bytearray()
        while size > 0:
            base = address & ~(BLOCK - 1)
            if base not in blocks:
                blocks[base] = inferior.read_memory(0xA0000000 + base, BLOCK).tobytes()
            part = min(size, base + BLOCK - address)
            out += blocks[base][address - base:address - base + part]
            address += part
            size -= part
        return bytes(out)
    return read


def owner(address):
    """Which mod's memory a problem is in. tools/addr2mod.py gives the function once a problem turns up."""
    if address < 0x400000:
        return "game"
    return f"mod {0x80000000 + address:#x}"


def capture(name):
    """Stops at each graphics task of the next whole frame and walks them with one running state, as the RSP does."""
    blocks = {}
    checker = None
    tasks = 0
    started = False
    while True:
        gdb.execute(f"hbreak *{TASK_START:#x}", to_string=True)
        resume()
        gdb.execute("delete", to_string=True)
        task = int(gdb.parse_and_eval("$a0")) & 0xFFFFFFFF
        if read32(task) != M_GFXTASK:
            continue
        swaps = read32(task - 0x10 + 8) & SWAP_FLAG
        if not started:                # Start on a frame boundary: the task after one that swapped.
            started = swaps != 0
            continue
        blocks.clear()
        if checker is None:
            checker = dl_check.Checker(read_rdram(blocks), owner, read32(task + 0x24) // 64)
        tasks += 1
        checker.walk(read32(task + 0x30) & 0xFFFFFF)
        if swaps:
            break
    row = checker.summary()
    row.update(scene=name, tasks=tasks, target=TARGET, list_peak=read32(LIST_PEAK))
    print("DL " + json.dumps(row), flush=True)
    shot(f"dl_{TARGET}_{name}")
    checked.append(row)
    return row
