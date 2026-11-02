#!/bin/sh
# The Phase 2 exit test, plus Phase 1 as a regression check.
cd "$(dirname "$0")/.." || exit 2
failed=0
echo "== patch engine, two test mods"
tests/run_ares.sh build/phase2/rom/phase2.z64 tests/gdb/phase2.gdb 240 || failed=1
tests/run_phase1.sh || failed=1
[ "$failed" = 0 ] && echo "PHASE 2 PASS" || echo "PHASE 2 FAIL"
exit "$failed"
