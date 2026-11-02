#!/bin/sh
# Melrode while moving, on vanilla and both mods, with ares's usual CPU and with its interpreter.
cd "$(dirname "$0")/.." || exit 2
echo 'source tests/gdb/perf_moving.py' > build/perf_moving.gdb
status=0
for mode in ${MODES:-recompiler interpreter}; do
    args=""
    [ "$mode" = interpreter ] && args="--setting General/ForceInterpreter=true"
    for target in vanilla eltale; do
        log="build/perf_moving_${target}_$mode.log"
        PERF_TARGET=$target ELTALE_LAYOUT=build/rom/perf-eltale-test/layout.json tests/run_ares.sh \
            "build/rom/perf-$target-test/perf-$target-test.z64" build/perf_moving.gdb 500 $args > "$log" 2>&1 || status=1
        grep -E '^(FAIL|FAULT)|CPU fault|Traceback|Error|TIMEOUT' "$log"
        echo "== $target, $mode"
        if [ "$target" = eltale ]; then python3 tests/perf_table.py /dev/null "$log"; else python3 tests/perf_table.py "$log" /dev/null; fi
    done
done
exit "$status"
