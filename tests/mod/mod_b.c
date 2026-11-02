// Test mod B: chains with mod A on the same functions, and hooks the function A patches.
#include "modding.h"
#include "results.h"

static u32 sLoggedDma;

RECOMP_HOOK("func_80031C40") void on_load_title(void) {
    log_event(EV_B_ENTRY);
}

RECOMP_HOOK_RETURN("func_80031C40") void after_load_title(void) {
    log_event(EV_B_RETURN);
}

RECOMP_HOOK("dma_write") void on_dma_b(u32 rom, void* ram, u32 size) {
    (void)ram;
    if (RESULTS[R_ARGS_B] == 0) {
        RESULTS[R_ARGS_B] = rom + size;
    }
    if (rom == 0xDA68F0 && !sLoggedDma) {
        sLoggedDma = 1;
        log_event(EV_B_DMA_ENTRY);
    }
}

RECOMP_HOOK_RETURN("dma_write") void after_dma_b(void) {
    if (sLoggedDma == 1) {
        sLoggedDma = 2;
        log_event(EV_B_DMA_RETURN);
    }
}

RECOMP_HOOK("func_80041ECC") void on_float_b(void) {
    u32 raw;
    __asm__ volatile("mfc1 %0, $f12" : "=r"(raw));
    RESULTS[R_FLOAT_ARG_B] = raw;
}

// Runs before mod A's return hook, which must still see the original f0.
RECOMP_HOOK_RETURN("func_80041ECC") void after_float_b(void) {
    u32 raw;
    __asm__ volatile("mfc1 %0, $f0" : "=r"(raw));
    RESULTS[R_FLOAT_RESULT_B] = raw;
    __asm__ volatile("li.s $f0, 789.0" : : : "$f0");
}
