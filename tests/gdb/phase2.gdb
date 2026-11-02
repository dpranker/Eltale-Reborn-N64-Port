# Each hook type, chains across two mods, a patch with hooks, float arguments, nesting, an overlay target
# and the import stubs. The test mods write results to uncached RAM at 0xA0700000 (tests/mod/results.h).
source tests/gdb/common.gdb
source build/phase2/rom/syms.gdb

define result
  set $r = {int}(0xA0700000+4*$arg0)
end

# The title overlay's load (other overlays share its addresses), then a function in it, then a later frame
# so its hook has run.
hbreak *0x80024260 if $a0 == 0xDA68F0
continue
check ($pc==0x80024260) "the title overlay loads with both mods installed"
delete
hbreak *0x801006D8
continue
check ($pc==0x801006D8) "the game reaches the title overlay"
delete
hbreak *0x800011DC
continue
check ($pc==0x800011DC) "the game keeps running after the title hook"
delete

printf "-- HOOK: integer arguments, displaced instructions\n"
result 1
check ($r==0x73A90) "first dma_write rom argument"
result 2
check ($r==(int)0x80096850) "first dma_write ram argument"
result 3
check ($r==0x3AD0) "first dma_write size argument"
result 25
check ($r==0x73A90+0x3AD0) "mod B saw the same arguments after mod A's hook"
result 4
set $entry_hits = $r
check ($entry_hits>=3) "dma_write entry hook ran repeatedly"

printf "-- HOOK_RETURN\n"
result 5
check ($r==$entry_hits) "dma_write return hook ran as often as the entry hook"
result 10
check ($r>0) "func_80041ECC return hook ran"

printf "-- Float arguments and results\n"
result 6
set $arg_a = $r
check ($arg_a!=0) "it got a real float argument, so the next checks mean something"
result 7
check ($r==$arg_a) "mod B saw f12 restored after mod A clobbered it"
result 8
set $f0_a = $r
check ($f0_a!=0) "it returned a real value"
result 9
check ($r==$f0_a) "mod A saw f0 restored after mod B clobbered it"
result 27
check ($r>0) "the early exit, whose result is set in the delay slot, was exercised"
result 28
check ($r==0) "the return hook always saw the delay slot's f0"
check ($f0_a!=0x43E40000&&$f0_a!=0x44454000) "the value isn't what a hook wrote into f0"

printf "-- Nesting and the per-thread slot\n"
result 13
set $before = $r
result 15
check ($r==$before) "a hook's return value survives a nested hooked call"
result 14
check ($r>0) "the nested function's return hook ran"
# From the mod's own nested call to osGetCount. The hook clobbers v0 as ordinary C code does, so a match means
# the hook read the real result and the trampoline gave it back to the caller.
result 11
set $count_caller = $r
check ($count_caller!=0) "osGetCount returned a count to the mod"
result 12
check ($r==$count_caller) "recomphook_get_return_s32 read the value the caller received"
result 26
check ($r==($count_caller&0xFFFF)) "recomphook_get_return_u16 read its low 16 bits"
check ({int}($rt_hook_frames+6*4)==0) "the game thread's frame slot is empty outside hooks"

printf "-- PATCH, with another mod's hooks on it\n"
result 16
check ($r==1) "the patch ran once"
set $count = {int}0xA0700000
check ($count==7) "seven events logged"
set $log = 0xA0700000+0x40*4
check ({int}($log+0)==0xB1) "1: mod B's entry hook runs before the patch"
check ({int}($log+4)==0xA0) "2: the patch"
check ({int}($log+8)==0xA3) "3: inside the patch, mod A's dma_write entry hook"
check ({int}($log+12)==0xB3) "4: then mod B's"
check ({int}($log+16)==0xB4) "5: return hooks reverse: mod B's first"
check ({int}($log+20)==0xA4) "6: then mod A's"
check ({int}($log+24)==0xB2) "7: mod B's return hook runs after the patch"

printf "-- Overlay target\n"
result 17
check ($r>=1) "the hook in the title overlay ran"

printf "-- Imports\n"
result 18
check ($r==12) "config number as u32"
result 20
check ($r==1250) "config number as double"
result 19
check ($r==2) "config enum, overridden on the command line"
result 21
check ($r==0) "dependency that's present"
result 22
check ($r==2) "dependency that's missing"
result 23
check ($r==0) "smooth transparency is off"
result 24
check ($r==0x100) "native library functions are no-ops returning 0"
check ({int}$rt_printf_count>=1) "printf counted"
check ({int}$rt_error==0) "the runtime reported no error"
finish_test
