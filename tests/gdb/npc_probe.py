# Lists the game's NPC records on Melrode's street at each story state, to explain the crowd in perf rows.
gdb.execute("source tests/gdb/perf_common.py")


def dump(label):
    count = read32(NPC_COUNT)
    rows = []
    for i in range(min(count, 32)):
        npc = NPCS + i * NPC_SIZE
        d = read32(npc + 0x80)
        rows.append(f"{read16(d + 2) if d else -1}@({read_float(npc + 0x14):.0f},{read_float(npc + 0x1C):.0f})")
    print(f"NPCS {label}: count={count} {' '.join(rows)}", flush=True)


if TARGET == "eltale":
    title_to_new_game()
    talk(6000)
    set_flag(16)
    print(f"FLAGS start {read32(FLAGS):08x} hour={read32(0x8007BA5C):#x}", flush=True)
else:
    new_game()
clear_scene()
melrode_street()
dump("street")
shot(f"npc_{TARGET}_street")
if TARGET == "eltale":
    def flag(bit):
        return inferior.read_memory(FLAGS + bit // 8, 1).tobytes()[0] >> (bit % 8) & 1

    bits = [b for b in range(0x300) if flag(b)]
    print(f"FLAGS set: {[hex(b) for b in bits]}; 0x74 is {flag(0x74)}", flush=True)
    addr = FLAGS + 0x74 // 8
    inferior.write_memory(addr, bytes([inferior.read_memory(addr, 1).tobytes()[0] & ~(1 << (0x74 % 8)) & 0xFF]))
    clear_scene()
    warp(0x1A)
    melrode_street()
    dump("0x74 cleared")
    shot("npc_eltale_cleared")
finish()
