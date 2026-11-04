#!/bin/sh
# The sprint toggle in the field, in menus and in a battle. See tests/gdb/sprint.py.
cd "$(dirname "$0")/.." || exit 2
echo 'source tests/gdb/sprint.py' > build/sprint.gdb
PERF_TARGET=eltale ELTALE_LAYOUT=build/rom/dev-glencoe/layout.json tests/run_ares.sh \
    build/rom/dev-glencoe/dev-glencoe.z64 build/sprint.gdb 300 > build/sprint.log 2>&1
status=$?
grep -E '^(AT|ok:|FAIL|FAULT|RESULT)|CPU fault|Traceback|TIMEOUT|Error' build/sprint.log | cut -c1-150
exit "$status"
