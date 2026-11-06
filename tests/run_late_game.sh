#!/bin/sh
# Solvaring on vanilla and Eltale, then the mod's debug jumps: the ending through the credits, the spell test, the
# hounds and the guns. Each runs under the fault detector and the display list checker.
cd "$(dirname "$0")/.." || exit 2
nrm=vendor/Eltale-Reborn/mods
status=0
echo 'source tests/gdb/boss.py' > build/boss.gdb
echo 'source tests/gdb/dev_scene.py' > build/dev.gdb
for target in vanilla eltale; do
    echo "== boss, $target"
    PERF_TARGET=$target ELTALE_LAYOUT=build/rom/perf-eltale-test/layout.json tests/run_ares.sh \
        "build/rom/perf-$target-test/perf-$target-test.z64" build/boss.gdb 400 > "build/boss_$target.log" 2>&1 || status=1
    grep -E '^(ok:|FAIL|FAULT)|CPU fault|Traceback|TIMEOUT' "build/boss_$target.log" | cut -c1-140
done
run_scene() {
    name="$1"; setting="$2"; polls="$3"; limit="$4"
    python3 tools/build_rom.py --out "build/rom/dev-$name" --name "dev-$name" \
        --hook-order eltale_reborn,quest64_modern_gameplay,test_input,test_perf \
        --mod "$nrm/quest64_modern_gameplay.nrm" --mod "${ELTALE_NRM:-$nrm/eltale_reborn.nrm}" --mod build/phase2/input --mod build/phase2/perf \
        --sprint-button L --set "eltale_reborn.dev_scene=$setting" > /dev/null || exit 2
    echo "== $name"
    DEV_SCENE_NAME="$name" DEV_SCENE_POLLS="$polls" PERF_TARGET=eltale ELTALE_LAYOUT="build/rom/dev-$name/layout.json" \
        tests/run_ares.sh "build/rom/dev-$name/dev-$name.z64" build/dev.gdb "$limit" > "build/dev_$name.log" 2>&1 || status=1
    grep -E '^(ok:|FAIL|FAULT)|CPU fault|Traceback|TIMEOUT' "build/dev_$name.log" | cut -c1-140
}
run_scene ending "The ending (after Mammon)" 70000 580
run_scene spells "Spell visuals test (Melrode)" 4800 130
run_scene hounds "Prologue: the hounds at the wall" 4800 130
run_scene guns "Act 5: the guns and the shot's flight" 4800 130
exit "$status"
