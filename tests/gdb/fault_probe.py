# Triggers one kind of fault through the test input mod, and reports whether ares raised it as a signal.
# KIND comes from the runner. Kind 0 triggers nothing, so a fault there means the detector is wrong.
gdb.execute("source tests/gdb/drive.py")
EXPECT_FAULTS = True
connect()
gdb.execute(f"hbreak *{POLL_ENTRY:#x}", to_string=True)
resume()
gdb.execute("delete", to_string=True)
write32(FAULT_KIND, KIND)
polls = read32(POLLS)
gdb.execute(f"hbreak *{POLL_ENTRY:#x} if {{int}}{POLLS:#x} >= {polls + 20}", to_string=True)
gdb.execute("continue", to_string=True)
result = faults[0][0] if faults else "none"
print(f"PROBE {KIND} {result} {faults[0][1]:#x}" if faults else f"PROBE {KIND} none", flush=True)
gdb.execute("detach", to_string=True)
gdb.execute("quit 0")
