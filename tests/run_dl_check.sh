#!/bin/sh
# Hand-built lists first, then real frames on vanilla and on both mods. Vanilla is the control: it must be clean.
cd "$(dirname "$0")/.." || exit 2
python3 tests/test_dl_check.py | tail -1
echo 'source tests/gdb/dl_scenes.py' > build/dl_scenes.gdb
status=0
for target in vanilla eltale; do
    log="build/dl_$target.log"
    PERF_TARGET=$target ELTALE_LAYOUT=build/rom/perf-eltale-test/layout.json tests/run_ares.sh \
        "build/rom/perf-$target-test/perf-$target-test.z64" build/dl_scenes.gdb 500 > "$log" 2>&1 || status=$?
    grep -E '^(ok:|FAIL|FAULT|RESULT)|CPU fault|Traceback|Error|TIMEOUT' "$log" | cut -c1-140
    python3 tests/dl_table.py "$log"
done
exit "$status"
