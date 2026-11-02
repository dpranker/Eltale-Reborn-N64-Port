#!/bin/sh
# The automated Phase 3 checks: the same script on vanilla and modded ROMs, then an idle run.
cd "$(dirname "$0")/.." || exit 2
for tag in vanilla gameplay; do
    printf "python TAG = '%s'\nsource tests/gdb/phase3.py\n" "$tag" > build/phase3_$tag.gdb
    echo "== $tag"
    tests/run_ares.sh build/rom/$tag-test/$tag-test.z64 build/phase3_$tag.gdb 240 > build/phase3_$tag.log 2>&1
    grep -E '^(METRIC|walks|meter)|Traceback|TIMEOUT' build/phase3_$tag.log
done
echo "== idle"
echo 'source tests/gdb/phase3_idle.py' > build/phase3_idle.gdb
tests/run_ares.sh build/rom/gameplay-test/gameplay-test.z64 build/phase3_idle.gdb "${IDLE_SECONDS:-180}" > build/phase3_idle.log 2>&1
grep -E '^METRIC|Traceback' build/phase3_idle.log
python3 tests/compare_phase3.py build/phase3_vanilla.log build/phase3_gameplay.log build/phase3_idle.log || failed=1

echo "== fault detector"
for kind in 0 1 2 3 4 5 6; do
    printf "python KIND = %d\nsource tests/gdb/fault_probe.py\n" "$kind" > build/fault_$kind.gdb
    result=$(tests/run_ares.sh build/rom/gameplay-test/gameplay-test.z64 build/fault_$kind.gdb 40 2>&1 | grep '^PROBE')
    echo "$result"
    case "$kind:$result" in
        "0:PROBE 0 none") ;;
        "5:PROBE 5 SIGBUS"*) ;;
        [1-6]:"PROBE $kind SIGFPE"*) ;;
        *) echo "FAIL: fault kind $kind wasn't reported as expected"; failed=1 ;;
    esac
done
[ -z "$failed" ] && echo "PHASE 3 PASS" || echo "PHASE 3 FAIL"
exit "${failed:-0}"
