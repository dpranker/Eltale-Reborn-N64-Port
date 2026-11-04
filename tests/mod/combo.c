// Test-only mod: watches Brian's staff swing from inside the game for tests/gdb/combo.py, and sets what it needs through
// the CPU. gdb writes go past the data cache, so the game keeps its own copy of anything hot, like an enemy's HP.
// Never part of a release ROM.
#include "modding.h"

typedef unsigned char u8;
typedef float f32;

#define BOX ((volatile u32*)0xA0710200)
#define B_SEED BOX[0]       // Pinned at each hit roll, 0 for no pin.
#define B_FACING BOX[1]     // Float, radians: the enemy's facing at each hit roll, relative to Brian. 0xFFFFFFFF for none.
#define B_PRESS_AT BOX[2]   // The timer value the swing handler should see A on, after its decrement. 0xFFFFFFFF for none.
#define B_POKES BOX[3]      // One-shot writes at the next poll: address, size, value from B_POKE.
#define B_STATE BOX[4]      // The cached player state and battle state, at each poll.
#define B_BATTLE BOX[5]
#define B_LOGS BOX[6]
#define B_HP BOX[7]         // The enemy's HP at each hit roll, 0 for no change. The game soon clamps it back to its real maximum.
#define B_POKE (&BOX[8])
#define B_LOG (&BOX[72])
#define MAX_LOGS 32
#define NONE 0xFFFFFFFFu

#define EV_ROLL 1
#define EV_HIT 2
#define EV_MISS 3
#define EV_BACKHAND 4
#define EV_PRESS 5
#define EV_HP 6

#define BUTTONS (*(volatile u32*)0xA0710000)
#define ACTOR ((u8*)0x8007BAB8)
#define PLAYER_STATE (*(u16*)ACTOR)
#define BATTLE_STATE (*(u16*)0x8008C592)
#define PAD_PRESSED (*(u16*)0x80092876)
#define RAND_SEED (*(u32*)0x8004D748)
#define ENEMY(i) ((u8*)0x8007C998 + (i) * 0x128)
#define STATE_SWING 13
#define PAD_A 0x8000
#define PAD_SWING 0xA000
#define PHYSICAL_HIT 0x8004

f32 func_80023210(f32 dx, f32 dz);

static s32 sSlot;
static s32 sBackhand;
static u32 sTimer;

static void log_it(u32 kind, u32 value) {
    if (B_LOGS < MAX_LOGS) {
        B_LOG[B_LOGS] = (kind << 24) | (value & 0xFFFFFF);
        B_LOGS = B_LOGS + 1;
    }
}

RECOMP_HOOK_RETURN("osContGetReadData") void combo_poll(void) {
    u32 i;

    for (i = 0; i < B_POKES; i++) {
        u32 address = B_POKE[i * 3];
        u32 size = B_POKE[i * 3 + 1];
        u32 value = B_POKE[i * 3 + 2];

        if (size == 2) {
            *(u16*)address = (u16)value;
        } else if (size == 1) {
            *(u8*)address = (u8)value;
        } else {
            *(u32*)address = value;
        }
    }
    B_POKES = 0;
    if (PLAYER_STATE != STATE_SWING) {
        sTimer = 0;
        sBackhand = 0;
    }
    B_STATE = PLAYER_STATE;
    B_BATTLE = BATTLE_STATE;
}

// The swing handler is patched by Eltale. This runs first, every frame of the swing.
RECOMP_HOOK("func_80004448") void combo_swing(u8* obj, u8* actor) {
    u32 timer = *(u16*)(actor + 4);

    // Only the second swing winds the timer back up. func_8001D8B0, which starts its animation, can't be hooked.
    if (sTimer != 0 && timer > sTimer) {
        sBackhand = 1;
        log_it(EV_BACKHAND, timer);
    }
    sTimer = timer;
    if ((PAD_PRESSED & PAD_SWING) != 0 && timer > 1) {
        log_it(EV_PRESS, timer - 1);
    }
    // The press goes in by the mailbox, so it takes the real input path and arrives on the next frame.
    BUTTONS = (B_PRESS_AT != NONE && timer - 2 == B_PRESS_AT && !sBackhand) ? PAD_A : 0;
}

RECOMP_HOOK("func_80006A74") void combo_roll(s32 slot, u8* obj) {
    u8* enemy = ENEMY(slot);
    union {
        u32 word;
        f32 value;
    } facing;

    if (PLAYER_STATE != STATE_SWING) {
        return;
    }
    sSlot = slot;
    log_it(EV_ROLL, slot);
    if (B_SEED != 0) {
        RAND_SEED = B_SEED;
    }
    if (B_HP != 0) {
        *(u16*)(enemy + 0xA) = (u16)B_HP;
    }
    if (B_FACING != NONE) {
        facing.word = B_FACING;
        *(f32*)(enemy + 0x34) = func_80023210(*(f32*)obj - *(f32*)(enemy + 0x24), *(f32*)(obj + 8) - *(f32*)(enemy + 0x2C)) +
                                facing.value;
    }
}

RECOMP_HOOK("func_8000ACC0") void combo_apply(s32 index, u32 power, s32 element, u32 flags) {
    if ((flags & 0xFFFF) == PHYSICAL_HIT) {
        log_it(EV_HIT, power & 0xFFFF);
    }
}

RECOMP_HOOK_RETURN("func_8000ACC0") void combo_applied(void) {
    if (PLAYER_STATE == STATE_SWING) {
        log_it(EV_HP, *(u16*)(ENEMY(sSlot) + 0xA));
    }
}

RECOMP_HOOK("func_8000B110") void combo_miss(void) {
    if (PLAYER_STATE == STATE_SWING) {
        log_it(EV_MISS, 0);
    }
}
