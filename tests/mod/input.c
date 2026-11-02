// Test-only mod: overlays controller input from a RAM mailbox, so gdb scripts can play the game.
// Never part of a release ROM. See tests/gdb/drive.py.
#include "modding.h"

#define MAILBOX ((volatile u32*)0xA0710000)
#define BUTTONS MAILBOX[0]
#define STICK MAILBOX[1]
#define POLLS MAILBOX[2]
#define FAULT_KIND MAILBOX[3]

typedef struct {
    u16 button;
    signed char stick_x;
    signed char stick_y;
    unsigned char errnum;
} ContPad;

static ContPad* sPad;

// Each kind of fault the real console can raise where PC doesn't. tests/gdb/fault_probe.py checks they're seen.
static void trigger_fault(u32 kind) {
    static volatile u32 words[2];
    volatile u32 sink;
    switch (kind) {
        case 1: // Invalid operation: 0 / 0.
            __asm__ volatile("mtc1 $zero, $f0\n\tmtc1 $zero, $f2\n\tdiv.s $f4, $f0, $f2" : : : "$f0", "$f2", "$f4");
            break;
        case 2: { // Float to int of NaN.
            u32 nan = 0x7FC00000;
            __asm__ volatile("mtc1 %0, $f0\n\ttrunc.w.s $f4, $f0" : : "r"(nan) : "$f0", "$f4");
            break;
        }
        case 3: { // Float to int out of range: 1e30.
            u32 big = 0x7149F2CA;
            __asm__ volatile("mtc1 %0, $f0\n\ttrunc.w.s $f4, $f0" : : "r"(big) : "$f0", "$f4");
            break;
        }
        case 4: { // Ordered compare with NaN.
            u32 nan = 0x7FC00000;
            __asm__ volatile("mtc1 %0, $f0\n\tmtc1 $zero, $f2\n\tc.lt.s $f0, $f2\n\tnop" : : "r"(nan) : "$f0", "$f2");
            break;
        }
        case 5: { // Unaligned load.
            u32 addr = (u32)&words[0] + 2;
            __asm__ volatile("lw %0, 0(%1)" : "=r"(sink) : "r"(addr));
            break;
        }
        case 6: { // Denormal input.
            u32 denormal = 1;
            __asm__ volatile("mtc1 %0, $f0\n\tadd.s $f4, $f0, $f0" : : "r"(denormal) : "$f0", "$f4");
            break;
        }
    }
}

RECOMP_HOOK("osContGetReadData") void input_before_read(ContPad* pad) {
    sPad = pad;
}

RECOMP_HOOK_RETURN("osContGetReadData") void input_after_read(void) {
    if (sPad != 0) {
        u32 stick = STICK;
        sPad->button |= (u16)BUTTONS;
        if (stick != 0) {
            sPad->stick_x = (signed char)(stick >> 8);
            sPad->stick_y = (signed char)stick;
        }
        sPad->errnum = 0;
    }
    POLLS = POLLS + 1;
    if (FAULT_KIND != 0) {
        u32 kind = FAULT_KIND;
        FAULT_KIND = 0;
        trigger_fault(kind);
    }
}
