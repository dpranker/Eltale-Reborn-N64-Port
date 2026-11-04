#!/bin/sh
# Every room's heaviest display list. Uses tests/build_dev_rom.sh's ROM, which has the mod that resets the count.
cd "$(dirname "$0")/.." || exit 2
echo 'source tests/gdb/room_sweep.py' > build/room_sweep.gdb
PERF_TARGET=eltale ELTALE_LAYOUT=build/rom/dev-glencoe/layout.json tests/run_ares.sh \
    build/rom/dev-glencoe/dev-glencoe.z64 build/room_sweep.gdb 1700 > build/room_sweep.log 2>&1
status=$?
grep -E '^(ok:|FAIL|FAULT|RESULT)|CPU fault|Traceback|TIMEOUT|Error' build/room_sweep.log | cut -c1-400
exit "$status"
