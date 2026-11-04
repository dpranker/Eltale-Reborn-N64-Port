#!/bin/sh
# Display list size in Glencoe Forest, with Eltale's ring lights lit. See tests/gdb/glencoe.py.
cd "$(dirname "$0")/.." || exit 2
echo 'source tests/gdb/glencoe.py' > build/glencoe.gdb
PERF_TARGET=eltale ELTALE_LAYOUT=build/rom/dev-glencoe/layout.json tests/run_ares.sh \
    build/rom/dev-glencoe/dev-glencoe.z64 build/glencoe.gdb 420 > build/glencoe.log 2>&1
status=$?
grep -E '^(AT|ok:|FAIL|FAULT|RESULT)|CPU fault|Traceback|TIMEOUT|Error' build/glencoe.log | cut -c1-150
exit "$status"
