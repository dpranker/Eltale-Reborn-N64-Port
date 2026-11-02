#!/bin/sh
# Frame times for the same scenes on vanilla and on both mods. Results go to build/perf_<target>.log and build/perf.json.
cd "$(dirname "$0")/.." || exit 2
status=0
for target in vanilla eltale; do
    echo "== $target"
    echo 'source tests/gdb/perf.py' > build/perf.gdb
    PERF_TARGET=$target ELTALE_LAYOUT=build/rom/perf-eltale-test/layout.json tests/run_ares.sh \
        "build/rom/perf-$target-test/perf-$target-test.z64" build/perf.gdb 900 > "build/perf_$target.log" 2>&1 || status=1
    grep -E '^(SCENE|SKIP|AT |ok:|FAIL|FAULT)|CPU fault|Traceback|Error|TIMEOUT' "build/perf_$target.log"
done
[ "$status" = 0 ] && python3 tests/perf_table.py build/perf_vanilla.log build/perf_eltale.log || { echo "PERF RUN FAILED"; exit 1; }
