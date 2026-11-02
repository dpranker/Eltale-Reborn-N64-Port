# Without an Expansion Pak: the loader shows its screen and stops, and the game never starts.
source tests/gdb/common.gdb
source build/phase1_syms.gdb

hbreak *$loader_halted
hbreak *0x80000C50
continue
check ($pc==$loader_halted) "the loader stops rather than starting the game"
delete
check ({int}0x80000318==0x400000) "osMemSize is 4 MB"
check ({int}0xA4400004==0x00200000) "VI shows the message's framebuffer"
check ({int}0xA4400000==0x0000311E) "VI is set to 16-bit"
dump binary memory build/nopak_fb.bin 0xA0200000 0xA0225800
finish_test
