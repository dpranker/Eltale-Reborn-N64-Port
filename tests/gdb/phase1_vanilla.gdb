# On the vanilla ROM: func_800471B0, which stage 1 replaces, doesn't run on the way to the title.
source tests/gdb/common.gdb

hbreak *0x800471B0
hbreak *0x80024260 if $a0 == 0xDA68F0
continue
check ($pc==0x80024260) "the title overlay loads without func_800471B0 running"
delete
finish_test
