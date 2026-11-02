// Test-only mod: measures frames for tests/gdb/perf.py, and with PERF_HUD also draws them on screen, for consoles
// with no gdb. Never part of a release ROM.
//
// A frame is one buffer swap, what the player sees, timed in retraces counted at the scheduler's own broadcast, so a frame's length doesn't
// depend on the clock speed. Count registers are only ever compared with a retrace measured in Count, so an overclocked console
// gets a correct share of its frame time too.
#include "modding.h"

#define PERF ((volatile u32*)0xA0710100)
#define P_RESET 0
#define P_FRAMES 1
#define P_RETRACES 2
#define P_COUNT 3
#define P_GAME_SUM 4
#define P_GAME_MAX 5
#define P_RCP_SUM 6
#define P_RCP_MAX 7
#define P_WRITEBACK_SUM 8
#define P_WRITEBACK_MAX 9
#define P_WRITEBACKS 10
#define P_HIST 11 // Frames that took 0, 1, ... 7 retraces, the last meaning 7 or more.
#define HIST_SIZE 8

#define M_GFXTASK 1

typedef struct {
    u32 type;
} OSTaskHead;

static u32 sPollCount;
static u32 sLastCount;
static u32 sTaskCount;
static u32 sRetraces;
static u32 sLastRetrace;
static u32 sSeenFrame;
static u32 sWritebackStart;
static u32 sFrameHasTask;
static u32 sLastGame;

static inline u32 read_count(void) {
    u32 count;
    __asm__ volatile("mfc0 %0, $9" : "=r"(count));
    return count;
}

static inline void add_max(u32 sum, u32 max, u32 value) {
    PERF[sum] = PERF[sum] + value;
    if (value > PERF[max]) {
        PERF[max] = value;
    }
}

#ifdef PERF_HUD
#define VI_WIDTH (*(volatile u32*)0xA4400008)
#define HUD_X 32
#define HUD_Y 16
#define HUD_CHARS 20
#define HUD_WINDOW 30
#define WHITE 0xFFFF
#define BLACK 0x0001

// 3x5 digits and the few letters the HUD uses, top row in the high bits, one bit a pixel.
static const u16 sFont[] = {
    0x7B6F, 0x2C97, 0x73E7, 0x73CF, 0x5BC9, 0x79CF, 0x79EF, 0x7292, 0x7BEF, 0x7BCF, // 0-9
    0x79E4, // F
    0x6BAD, // R
    0x5B7D, // W
    0x796F, // G
    0x0000, // space
    0x0002, // .
};
enum { CH_F = 10, CH_R, CH_W, CH_G, CH_SPACE, CH_DOT };

static unsigned char sText[HUD_CHARS];
static u32 sTextLen;
static u32 sWinFrames, sWinRetraces, sWinCount, sWinGame, sWinRcp, sWinWorst;

static void put_char(u32 ch) {
    if (sTextLen < HUD_CHARS) {
        sText[sTextLen++] = ch;
    }
}

static void put_number(u32 value) {
    u32 divisor = 1;
    while (value / divisor >= 10) {
        divisor *= 10;
    }
    for (; divisor != 0; divisor /= 10) {
        put_char((value / divisor) % 10);
    }
}

// F fps, W the longest frame in retraces, G the game thread and R the RCP, each as a percentage of a 30 fps frame.
static void hud_update(u32 retraces, u32 count, u32 game, u32 rcp) {
    sWinFrames++;
    sWinRetraces += retraces;
    sWinCount += count;
    sWinGame += game;
    sWinRcp += rcp;
    if (retraces > sWinWorst) {
        sWinWorst = retraces;
    }
    if (sWinFrames < HUD_WINDOW || sWinRetraces == 0) {
        return;
    }
    u32 budget = sWinCount / sWinRetraces * 2 / 100 * sWinFrames;
    u32 tenths = sWinFrames * 599 / sWinRetraces;
    sTextLen = 0;
    put_char(CH_F);
    put_number(tenths / 10);
    put_char(CH_DOT);
    put_number(tenths % 10);
    put_char(CH_SPACE);
    put_char(CH_W);
    put_number(sWinWorst);
    put_char(CH_SPACE);
    put_char(CH_G);
    put_number(budget ? sWinGame / budget : 0);
    put_char(CH_SPACE);
    put_char(CH_R);
    put_number(budget ? sWinRcp / budget : 0);
    sWinFrames = sWinRetraces = sWinCount = sWinGame = sWinRcp = sWinWorst = 0;
}

// Writes straight into the finished frame, uncached, just before it's shown.
static void hud_draw(u32 framebuffer) {
    u32 width = VI_WIDTH & 0xFFF;
    volatile u16* fb = (volatile u16*)((framebuffer & 0x1FFFFFFF) | 0xA0000000);
    u32 x, y, c;
    if (width == 0 || sTextLen == 0) {
        return;
    }
    for (y = 0; y < 14; y++) {
        volatile u16* row = fb + (HUD_Y + y) * width + HUD_X;
        for (x = 0; x < sTextLen * 8 + 4; x++) {
            row[x] = BLACK;
        }
    }
    for (c = 0; c < sTextLen; c++) {
        u32 glyph = sFont[sText[c]];
        for (y = 0; y < 10; y++) {
            volatile u16* row = fb + (HUD_Y + 2 + y) * width + HUD_X + 2 + c * 8;
            u32 bits = glyph >> ((4 - y / 2) * 3);
            for (x = 0; x < 6; x++) {
                if (bits & (4 >> (x / 2))) {
                    row[x] = WHITE;
                }
            }
        }
    }
}
#endif

// Runs once per retrace. The game's own counter at 0x8007B2D0 won't do, because the game resets it.
RECOMP_HOOK("nnScEventBroadcast") void perf_on_retrace(void) {
    sRetraces++;
}

RECOMP_HOOK("osContGetReadData") void perf_on_poll(void) {
    sPollCount = read_count();
}

// The game thread's work for a frame: its poll to the finished display list. The task itself can't mark the end,
// because nnScWaitTaskReady holds it until a framebuffer is free.
RECOMP_HOOK_RETURN("func_800011DC") void perf_on_list_built(void) {
    sLastGame = read_count() - sPollCount;
}

// A frame can take more than one graphics task, and only the last swaps. The RCP's time runs from the first.
RECOMP_HOOK("osSpTaskLoad") void perf_on_task(OSTaskHead* task) {
    if (task->type == M_GFXTASK && !sFrameHasTask) {
        sFrameHasTask = 1;
        sTaskCount = read_count();
    }
}

// nnScExecuteGraphics calls this only after both the RSP and the RDP have finished the frame.
RECOMP_HOOK("osViSwapBuffer") void perf_on_swap(u32 framebuffer) {
    u32 now = read_count();
    u32 retrace = sRetraces;
    u32 retraces = retrace - sLastRetrace;
    u32 rcp = sFrameHasTask ? now - sTaskCount : 0;
    sFrameHasTask = 0;
    if (PERF[P_RESET] != 0) {
        u32 i;
        for (i = 0; i < P_HIST + HIST_SIZE; i++) {
            PERF[i] = 0;
        }
        sSeenFrame = 0;
    }
    if (sSeenFrame) {
        u32 count = now - sLastCount;
        PERF[P_FRAMES] = PERF[P_FRAMES] + 1;
        PERF[P_RETRACES] = PERF[P_RETRACES] + retraces;
        PERF[P_COUNT] = PERF[P_COUNT] + count;
        add_max(P_GAME_SUM, P_GAME_MAX, sLastGame);
        add_max(P_RCP_SUM, P_RCP_MAX, rcp);
        PERF[P_HIST + (retraces < HIST_SIZE ? retraces : HIST_SIZE - 1)] += 1;
#ifdef PERF_HUD
        hud_update(retraces, count, sLastGame, rcp);
#endif
    }
    sSeenFrame = 1;
    sLastCount = now;
    sLastRetrace = retrace;
#ifdef PERF_HUD
    hud_draw(framebuffer);
#else
    (void)framebuffer;
#endif
}

RECOMP_HOOK("osWritebackDCacheAll") void perf_on_writeback(void) {
    sWritebackStart = read_count();
}

RECOMP_HOOK_RETURN("osWritebackDCacheAll") void perf_after_writeback(void) {
    PERF[P_WRITEBACKS] = PERF[P_WRITEBACKS] + 1;
    add_max(P_WRITEBACK_SUM, P_WRITEBACK_MAX, read_count() - sWritebackStart);
}
