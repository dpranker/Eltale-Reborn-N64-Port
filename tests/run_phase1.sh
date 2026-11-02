#!/bin/sh
# The Phase 1 exit test: the loader with and without an Expansion Pak, plus a check on vanilla that the
# function stage 1 replaces doesn't run on the way to the title.
cd "$(dirname "$0")/.." || exit 2
failed=0
run() { echo "== $1"; shift; tests/run_ares.sh "$@" || failed=1; }
run "vanilla: func_800471B0 stays unused" build/vanilla.z64 tests/gdb/phase1_vanilla.gdb 420
run "patched, Expansion Pak" build/phase1.z64 tests/gdb/phase1.gdb 420
run "patched, no Expansion Pak" build/phase1.z64 tests/gdb/phase1_nopak.gdb 120 --setting Nintendo64/ExpansionPak=false
[ "$failed" = 0 ] && echo "PHASE 1 PASS" || echo "PHASE 1 FAIL"
exit "$failed"
