// Test mod A: a patch, entry and return hooks, float arguments, an overlay target, nesting and every import.
#include "modding.h"
#include "results.h"

RECOMP_IMPORT(".", void ambience_frame(void))
RECOMP_IMPORT(".", u32 ambience_set(u32 a))

static u32 sLoggedDma;
static u32 sEarlyExit;
static volatile u32 sInNestedCall;

// PATCH: loads the title overlay as the original does, so the game still works.
RECOMP_PATCH void func_80031C40(void) {
    RESULTS[R_PATCH_HITS] = RESULTS[R_PATCH_HITS] + 1;
    log_event(EV_A_PATCH);
    dma_write(0xDA68F0, (void*)0x80100000, 0xDC1620 - 0xDA68F0);
}

// HOOK: integer arguments, on a function whose first two instructions get displaced.
RECOMP_HOOK("dma_write") void on_dma(u32 rom, void* ram, u32 size) {
    if (RESULTS[R_DMA_ENTRY_HITS] == 0) {
        RESULTS[R_FIRST_DMA_ROM] = rom;
        RESULTS[R_FIRST_DMA_RAM] = (u32)ram;
        RESULTS[R_FIRST_DMA_SIZE] = size;

        RESULTS[R_CONFIG_U32] = recomp_get_config_u32("sample_number");
        RESULTS[R_CONFIG_ENUM] = recomp_get_config_u32("sample_enum");
        RESULTS[R_CONFIG_DOUBLE_X100] = (u32)(recomp_get_config_double("sample_number") * 100.0);
        RESULTS[R_DEP_FOUND] = recomp_is_dependency_met("test_mod_b");
        RESULTS[R_DEP_MISSING] = recomp_is_dependency_met("not_a_mod");
        RESULTS[R_SMOOTH] = recomp_get_smooth_transparency();
        ambience_frame();
        RESULTS[R_NATIVE] = ambience_set(7) + 0x100;
        recomp_printf("hello %d\n", 1);
    }
    RESULTS[R_DMA_ENTRY_HITS] = RESULTS[R_DMA_ENTRY_HITS] + 1;
    if (rom == 0xDA68F0 && !sLoggedDma) {
        sLoggedDma = 1;
        log_event(EV_A_DMA_ENTRY);
    }
}

// HOOK_RETURN with nesting: this hook calls another function with a return hook, then reads its own value.
RECOMP_HOOK_RETURN("dma_write") void after_dma(void) {
    s32 before = recomphook_get_return_s32();
    u32 count;
    sInNestedCall = 1;
    count = osGetCount();
    sInNestedCall = 0;
    s32 after = recomphook_get_return_s32();

    RESULTS[R_DMA_RETURN_HITS] = RESULTS[R_DMA_RETURN_HITS] + 1;
    RESULTS[R_NEST_BEFORE] = before;
    RESULTS[R_NEST_AFTER] = after;
    // What the caller saw, after the inner trampoline restored its registers.
    RESULTS[R_COUNT_RETURN] = count;
    if (sLoggedDma == 1) {
        sLoggedDma = 2;
        log_event(EV_A_DMA_RETURN);
    }
}

RECOMP_HOOK_RETURN("osGetCount") void after_count(void) {
    // Only this mod's own call, since the hook also runs for every other osGetCount in the game.
    if (sInNestedCall) {
        RESULTS[R_COUNT_SEEN_BY_HOOK] = recomphook_get_return_s32();
        RESULTS[R_U16] = recomphook_get_return_u16();
    }
    RESULTS[R_NEST_INNER] = RESULTS[R_NEST_INNER] + 1;
}

// HOOK: a float argument, read raw because the function's real signature isn't known. It clobbers f12 for mod
// B's hook to detect, and it's first in the chain.
RECOMP_HOOK("func_80041ECC") void on_float(s32 a0) {
    u32 raw;
    __asm__ volatile("mfc1 %0, $f12" : "=r"(raw));
    RESULTS[R_FLOAT_ARG] = raw;
    sEarlyExit = (a0 >> 3) == 0;
    __asm__ volatile("li.s $f12, 123.0" : : : "$f12");
}

// HOOK_RETURN: this function exits early when a0 >> 3 is 0, through `jr ra; mov.s $f0, $f12`, so a hook only sees
// the right f0 if it runs after the delay slot. The hook also clobbers f0, for the game to be affected if it isn't restored.
RECOMP_HOOK_RETURN("func_80041ECC") void after_float(void) {
    u32 f0, f12;
    __asm__ volatile("mfc1 %0, $f0\n\tmfc1 %1, $f12" : "=r"(f0), "=r"(f12));
    RESULTS[R_FLOAT_RESULT] = f0;
    RESULTS[R_FLOAT_HITS] = RESULTS[R_FLOAT_HITS] + 1;
    if (sEarlyExit) {
        if (f0 == f12) {
            RESULTS[R_DELAY_SLOT_OK] = RESULTS[R_DELAY_SLOT_OK] + 1;
        } else {
            RESULTS[R_DELAY_SLOT_BAD] = RESULTS[R_DELAY_SLOT_BAD] + 1;
        }
    }
    __asm__ volatile("li.s $f0, 456.0" : : : "$f0");
}

// HOOK in the title overlay, which shares its address with the other overlays.
RECOMP_HOOK("func_801006D8_ovl_title") void on_title(void) {
    RESULTS[R_TITLE_OVERLAY_HITS] = RESULTS[R_TITLE_OVERLAY_HITS] + 1;
}
