# With an Expansion Pak: the blob and magic word are in place before the game thread starts, stage 1
# doesn't run again, and the game reaches the title screen.
source tests/gdb/common.gdb
source build/phase1_syms.gdb

# The game thread's entry, which only runs after the loader returns. ares checks breakpoints between
# recompiled blocks, so tests must break on function entries, never mid-function.
hbreak *0x80000C50
continue
delete
check ($pc==0x80000C50) "the game thread starts after the loader"

check ({int}0x80000318==0x800000) "osMemSize is 8 MB"
check ({int}0x807FFFF0==0x454C5441) "magic word is written"

define blob_word
  set $blob_i = $arg0
  set $blob_want = (int)(($blob_i * 0x01000193) ^ 0xE17A1E00)
  check ({int}(0x80400000+$blob_i*4)==$blob_want) "blob word matches"
end
blob_word 0
blob_word 1
blob_word 0x1000
blob_word 0x2AAAA
blob_word 0x53FFF

# The same check over a stretch that crosses the cache sizes.
set $i = 0x20000
set $bad = 0
while $i < 0x20400
  if {int}(0x80400000 + $i * 4) != (int)(($i * 0x01000193) ^ 0xE17A1E00)
    set $bad = $bad + 1
  end
  set $i = $i + 1
end
check ($bad==0) "a 4 KB stretch of the blob matches"

# Stage 1 must not run again, and the title overlay has to load (ROM address in $a0).
hbreak *$loader_boot
hbreak *0x80024260 if $a0 == 0xDA68F0
continue
check ($pc==0x80024260) "the title overlay loads, and stage 1 didn't run again"
delete

# A function in the title overlay. Other overlays share this address, so also compare its first word with
# the ROM's copy of the title overlay ($title_word, generated into build/ so no ROM bytes get committed).
hbreak *0x801006D8
continue
check ($pc==0x801006D8) "the game reaches a title screen function"
check ({int}0x801006D8==$title_word) "the code there is the title overlay's"
delete
check ({int}0x807FFFF0==0x454C5441) "the magic word survives to the title"
finish_test
