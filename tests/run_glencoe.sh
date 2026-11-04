#!/bin/sh
# Display list size in Glencoe Forest, with Eltale's ring lights lit. See tests/gdb/glencoe.py.
cd "$(dirname "$0")/.." || exit 2
nrm=vendor/Eltale-Reborn/mods
echo 'source tests/gdb/glencoe.py' > build/glencoe.gdb
python3 tools/build_rom.py --out "build/rom/dev-glencoe" --name "dev-glencoe" \
        --hook-order eltale_reborn,quest64_modern_gameplay,test_input,test_perf,test_combo \
        --mod "$nrm/quest64_modern_gameplay.nrm" --mod "source/1.1.3/eltale_reborn.nrm" --mod build/phase2/input --mod build/phase2/perf --mod build/phase2/combo \
        --sprint-button L > /dev/null || exit 2
PERF_TARGET=eltale ELTALE_LAYOUT=build/rom/dev-glencoe/layout.json tests/run_ares.sh \
    build/rom/dev-glencoe/dev-glencoe.z64 build/glencoe.gdb 420 > build/glencoe.log 2>&1
status=$?
grep -E '^(AT|ok:|FAIL|FAULT|RESULT)|CPU fault|Traceback|TIMEOUT|Error' build/glencoe.log | cut -c1-150
exit "$status"
