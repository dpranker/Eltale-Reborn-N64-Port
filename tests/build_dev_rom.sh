#!/bin/sh
# Builds build/rom/dev-glencoe: both mods plus the test mods. Used by test-glencoe, test-sweep and test-sprint.
cd "$(dirname "$0")/.." || exit 2
nrm=vendor/Eltale-Reborn/mods
python3 tools/build_rom.py --out "build/rom/dev-glencoe" --name "dev-glencoe" \
        --hook-order eltale_reborn,quest64_modern_gameplay,test_input,test_perf,test_combo \
        --mod "$nrm/quest64_modern_gameplay.nrm" --mod "$nrm/eltale_reborn.nrm" --mod build/phase2/input --mod build/phase2/perf --mod build/phase2/combo > /dev/null || exit 2
