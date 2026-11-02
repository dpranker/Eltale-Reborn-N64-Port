#!/bin/sh
# Builds N64Recomp's RecompModTool without cmake, for packaging the test mod the way real mods are packaged.
# usage: tools/build_modtool.sh <output binary>
set -e
out="$(realpath -m "$1")"
src="$(dirname "$0")/../vendor/Eltale-Reborn-DC-Port/tools/N64Recomp"
cd "$src"
obj="$(dirname "$out")/modtool_obj"
mkdir -p "$obj"
inc="-Iinclude -Isrc -Ilib/ELFIO -Ilib/fmt/include -Ilib/tomlplusplus/include -Ilib/rabbitizer/include -Ilib/rabbitizer/cplusplus/include -Ilib/rabbitizer/tables"
find lib/rabbitizer/src -name '*.c' | xargs -P "$(nproc)" -I{} sh -c \
    "gcc -std=c11 -O1 -w $inc -c {} -o \"$obj/\$(echo {} | tr '/' '_').o\""
{ find lib/rabbitizer/cplusplus/src -name '*.cpp'; echo src/elf.cpp; echo src/symbol_lists.cpp; echo src/config.cpp; echo src/mod_symbols.cpp; echo RecompModTool/main.cpp; } | \
    xargs -P "$(nproc)" -I{} sh -c \
    "g++ -std=c++20 -O1 -w -DFMT_HEADER_ONLY $inc -c {} -o \"$obj/\$(echo {} | tr '/' '_').o\""
g++ "$obj"/*.o -o "$out"
