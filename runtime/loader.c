// Stage 1 loader. Lives in place of func_800471B0, 64DD library code the game never runs (the PC and
// Dreamcast builds stub it). A patched jal in func_800004B0 calls loader_boot in place of
// osCreatePiManager, which is after PI init and before the game thread exists, so no hooked function
// has run yet.

#include "ultra.h"
#include "loader_config.h"

#define LOADER_DONE_MAGIC 0x454C5441 // "ELTA"
#define MEM_8MB 0x800000

static void wait_for_pi_read(u32 rom, void* ram, u32 size) {
    OSMesgQueue queue;
    OSMesg message;
    OSIoMesg io;

    osCreateMesgQueue(&queue, &message, 1);
    osInvalDCache(ram, size);
    osPiStartDma(&io, OS_MESG_PRI_NORMAL, OS_READ, rom, ram, size, &queue);
    // This thread is the only idle thread, and libultra can't dispatch with nothing runnable, so it can't block.
    while (osRecvMesg(&queue, 0, OS_MESG_NOBLOCK) != 0) {
    }
}

// --- The screen shown without an Expansion Pak ---

#define FB ((volatile u16*)0xA0200000)
#define FB_WIDTH 320
#define FB_HEIGHT 240
#define GLYPH_SCALE 2
#define COLOR_TEXT 0xFFFF
#define COLOR_BACK 0x0001

#define VI_REG(n) (*(volatile u32*)(0xA4400000 + (n)))

// Five columns per glyph, bit 0 at the top. Only the letters of the message.
static const struct {
    char c;
    u8 cols[5];
} sGlyphs[] = {
    { 'A', { 0x7E, 0x09, 0x09, 0x09, 0x7E } },
    { 'D', { 0x7F, 0x41, 0x41, 0x22, 0x1C } },
    { 'E', { 0x7F, 0x49, 0x49, 0x49, 0x41 } },
    { 'I', { 0x41, 0x41, 0x7F, 0x41, 0x41 } },
    { 'K', { 0x7F, 0x08, 0x14, 0x22, 0x41 } },
    { 'N', { 0x7F, 0x04, 0x08, 0x10, 0x7F } },
    { 'O', { 0x3E, 0x41, 0x41, 0x41, 0x3E } },
    { 'P', { 0x7F, 0x09, 0x09, 0x09, 0x06 } },
    { 'Q', { 0x3E, 0x41, 0x51, 0x21, 0x5E } },
    { 'R', { 0x7F, 0x09, 0x19, 0x29, 0x46 } },
    { 'S', { 0x46, 0x49, 0x49, 0x49, 0x31 } },
    { 'U', { 0x3F, 0x40, 0x40, 0x40, 0x3F } },
    { 'X', { 0x63, 0x14, 0x08, 0x14, 0x63 } },
};

static void draw_text(const char* text, s32 x, s32 y) {
    for (; *text != '\0'; text++, x += 6 * GLYPH_SCALE) {
        for (u32 g = 0; g < sizeof(sGlyphs) / sizeof(sGlyphs[0]); g++) {
            if (sGlyphs[g].c != *text) {
                continue;
            }
            for (s32 col = 0; col < 5 * GLYPH_SCALE; col++) {
                u8 bits = sGlyphs[g].cols[col / GLYPH_SCALE];
                for (s32 row = 0; row < 7 * GLYPH_SCALE; row++) {
                    if (bits & (1 << (row / GLYPH_SCALE))) {
                        FB[(y + row) * FB_WIDTH + x + col] = COLOR_TEXT;
                    }
                }
            }
        }
    }
}

static void expansion_pak_required(void) {
    osSetIntMask(OS_IM_NONE);

    for (s32 i = 0; i < FB_WIDTH * FB_HEIGHT; i++) {
        FB[i] = COLOR_BACK;
    }
    draw_text("EXPANSION PAK", (FB_WIDTH - 13 * 6 * GLYPH_SCALE) / 2, 96);
    draw_text("REQUIRED", (FB_WIDTH - 8 * 6 * GLYPH_SCALE) / 2, 128);

    // NTSC, 320x240, 16-bit (the values of libultra's LAN1 mode). The ROM is the US release.
    VI_REG(0x04) = 0x00200000;
    VI_REG(0x08) = FB_WIDTH;
    VI_REG(0x0C) = 0;
    VI_REG(0x14) = 0x03E52239;
    VI_REG(0x18) = 0x0000020D;
    VI_REG(0x1C) = 0x00000C15;
    VI_REG(0x20) = 0x0C150C15;
    VI_REG(0x24) = 0x006C02EC;
    VI_REG(0x28) = 0x002501FF;
    VI_REG(0x2C) = 0x000E0204;
    VI_REG(0x30) = 0x00000200;
    VI_REG(0x34) = 0x00000400;
    VI_REG(0x00) = 0x0000311E;

    // A label for tests/gdb/phase1_nopak.gdb to stop at.
    __asm__(".globl loader_halted\nloader_halted:");
    for (;;) {
    }
}

// --- Entry ---

void loader_boot(s32 pri, OSMesgQueue* cmdQ, OSMesg* cmdBuf, s32 cmdMsgCnt) {
    osCreatePiManager(pri, cmdQ, cmdBuf, cmdMsgCnt);

    if (osMemSize < MEM_8MB) {
        expansion_pak_required();
    }

    wait_for_pi_read(LOADER_ROM_ADDR, (void*)LOADER_RAM_ADDR, LOADER_SIZE);
    osInvalICache((void*)LOADER_RAM_ADDR, LOADER_SIZE);
    osInvalDCache((void*)LOADER_RAM_ADDR, LOADER_SIZE);

    *(volatile u32*)LOADER_MAGIC_ADDR = LOADER_DONE_MAGIC;
    osWritebackDCache((void*)LOADER_MAGIC_ADDR, sizeof(u32));
}
