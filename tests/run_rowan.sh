#!/bin/sh
# Rowan Berry: cures in battle, stays in the bag in the field. See tests/gdb/rowan.py.
cd "$(dirname "$0")/.." || exit 2
echo 'source tests/gdb/rowan.py' > build/rowan.gdb
PERF_TARGET=eltale ELTALE_LAYOUT=build/rom/dev-glencoe/layout.json tests/run_ares.sh \
    build/rom/dev-glencoe/dev-glencoe.z64 build/rowan.gdb 300 > build/rowan.log 2>&1
status=$?
grep -E '^(AT|ok:|FAIL|FAULT|RESULT)|CPU fault|Traceback|TIMEOUT|Error' build/rowan.log | cut -c1-150
exit "$status"
