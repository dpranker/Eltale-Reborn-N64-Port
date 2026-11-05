#!/bin/sh
# Timed second swings and back attacks, with the options on and off. Critical hits are off because they roll from the CPU
# timer, which the test can't pin, and they're the same 1.5 times as a back attack.
cd "$(dirname "$0")/.." || exit 2
nrm=vendor/Eltale-Reborn/mods
status=0
echo 'source tests/gdb/combo.py' > build/combo.gdb
run() {
    name="$1"; shift
    python3 tools/build_rom.py --out "build/rom/dev-combo-$name" --name "dev-combo-$name" \
        --hook-order eltale_reborn,quest64_modern_gameplay,test_input,test_perf,test_combo \
        --mod "$nrm/quest64_modern_gameplay.nrm" --mod "$nrm/eltale_reborn.nrm" --mod build/phase2/input --mod build/phase2/perf --mod build/phase2/combo \
        --set eltale_reborn.jp_critical_hits=Off "$@" > /dev/null || exit 2
    echo "== options $name"
    PERF_TARGET=eltale ELTALE_LAYOUT="build/rom/dev-combo-$name/layout.json" tests/run_ares.sh \
        "build/rom/dev-combo-$name/dev-combo-$name.z64" build/combo.gdb 400 > "build/combo_$name.log" 2>&1 || status=1
    grep -E '^(ok:|FAIL|FAULT|RESULT)|CPU fault|Traceback|TIMEOUT|Error' "build/combo_$name.log" | cut -c1-150
}
run on
COMBO_OFF=1 run off --set eltale_reborn.jp_timed_hits=Off --set eltale_reborn.jp_back_attacks=Off
exit "$status"
