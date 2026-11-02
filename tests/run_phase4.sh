#!/bin/sh
# The automated Phase 4 route: new game to a save at the inn, then a fresh boot and a load.
cd "$(dirname "$0")/.." || exit 2
pak="build/ares/saves/Nintendo 64/eltale-test.pak"
rm -f "$pak"
echo 'source tests/gdb/phase4_story.py' > build/phase4_story.gdb
echo 'source tests/gdb/phase4_load.py' > build/phase4_load.gdb
echo "== story"
# ares writes the Controller Pak file every 30 seconds, so keep it running past that.
KEEP_SECONDS=35 tests/run_ares.sh build/rom/eltale-test/eltale-test.z64 build/phase4_story.gdb 300 --setting General/AutoSaveMemory=true > build/phase4_story.log 2>&1
story=$?
grep -E '^(AT |ok:|FAIL|FAULT)|CPU fault|Traceback|TIMEOUT' build/phase4_story.log
echo "== load"
tests/run_ares.sh build/rom/eltale-test/eltale-test.z64 build/phase4_load.gdb 120 > build/phase4_load.log 2>&1
load=$?
grep -E '^(AT |ok:|FAIL|FAULT)|CPU fault|Traceback|TIMEOUT' build/phase4_load.log
[ "$story" = 0 ] && [ "$load" = 0 ] && echo "PHASE 4 ROUTE PASS" || { echo "PHASE 4 ROUTE FAIL"; exit 1; }
