// Test-only mod: overlays controller input from a RAM mailbox, so gdb scripts can play the game.
// Never part of a release ROM. See tests/gdb/drive.py.
#include "modding.h"

#define MAILBOX ((volatile u32*)0xA0710000)
#define BUTTONS MAILBOX[0]
#define STICK MAILBOX[1]
#define POLLS MAILBOX[2]

typedef struct {
    u16 button;
    signed char stick_x;
    signed char stick_y;
    unsigned char errnum;
} ContPad;

static ContPad* sPad;

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
}
