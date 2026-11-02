// The imports the mods expect from the PC runtime. tools/link_mods.py generates a stub per mod and import
// that puts the mod's index in the argument after the mod's own, then jumps here.

#include "ultra.h"
#include "modrt_config.h"

// Written by return-hook trampolines: this thread's current frame. Indexed by thread id. A trampoline saves
// and restores the slot, so a hook that calls another hooked function still reads its own values.
#define HOOK_FRAME_SLOTS 32
#define FRAME_V0 0x28
#define FRAME_V1 0x2C

void* rt_hook_frames[HOOK_FRAME_SLOTS];

// Read by tools and tests.
volatile u32 rt_printf_count;
volatile const char* rt_printf_last;
volatile const char* rt_error;

extern struct OSThread_s* __osRunningThread;

static void* current_frame(void) {
    u32 id = *(s32*)((u8*)__osRunningThread + 0x14);
    return rt_hook_frames[id & (HOOK_FRAME_SLOTS - 1)];
}

static void fatal(const char* message) {
    rt_error = message;
    osWritebackDCache((void*)&rt_error, sizeof(rt_error));
    for (;;) {
    }
}

s32 rt_get_return_s32(void) {
    void* frame = current_frame();
    if (frame == 0) {
        fatal("recomphook_get_return outside a return hook");
    }
    return *(s32*)((u8*)frame + FRAME_V0);
}

u32 rt_get_return_u16(void) {
    return rt_get_return_s32() & 0xFFFF;
}

// --- Config: a generated table of compile-time values, reached through a cache keyed by the string's address ---

#define CONFIG_CACHE_SIZE 64

static const ModConfigValue* sConfigCache[CONFIG_CACHE_SIZE];

static s32 string_equal(const char* a, const char* b) {
    while (*a != '\0' && *a == *b) {
        a++;
        b++;
    }
    return *a == *b;
}

static const ModConfigValue* find_config(const char* key, u32 mod) {
    u32 hash = (((u32)key >> 2) ^ (mod * 31)) & (CONFIG_CACHE_SIZE - 1);
    const ModConfigValue* cached = sConfigCache[hash];
    if (cached != 0 && cached->keyAddr == key) {
        return cached;
    }
    for (u32 i = 0; i < gModConfigCount; i++) {
        const ModConfigValue* v = &gModConfig[i];
        if (v->mod == mod && string_equal(v->key, key)) {
            ((ModConfigValue*)v)->keyAddr = key;
            sConfigCache[hash] = v;
            return v;
        }
    }
    fatal(key);
    return 0;
}

u32 rt_config_u32(const char* key, u32 mod) {
    return find_config(key, mod)->u;
}

double rt_config_double(const char* key, u32 mod) {
    return find_config(key, mod)->d;
}

// --- Everything else ---

// recomp_is_dependency_met: 0 is found, 2 is not found (the PC runtime's values).
u32 rt_is_dependency_met(const char* id) {
    for (u32 i = 0; i < gModIdCount; i++) {
        if (string_equal(gModIds[i], id)) {
            return 0;
        }
    }
    return 2;
}

u32 rt_smooth_transparency(void) {
    return RT_SMOOTH_TRANSPARENCY;
}

void rt_printf(const char* format) {
    rt_printf_count++;
    rt_printf_last = format;
}

// Runs before every RSP task. See RUNTIME_HOOKS in tools/link_mods.py.
void rt_before_task(void) {
    osWritebackDCacheAll();
}

// The gameplay mod's sprint reads button bit 0x40, which no N64 button sets. Pressing the mapped button also
// sets that bit. The pad pointer only has to last until the same call returns.
#define SPRINT_BIT 0x0040
#define PAD_COUNT 4

typedef struct {
    u16 button;
    s8 stick_x;
    s8 stick_y;
    u8 errnum;
} ContPad;

static ContPad* sPads;

void rt_pads_before_read(ContPad* pads) {
    sPads = pads;
}

void rt_pads_after_read(void) {
    for (s32 i = 0; i < PAD_COUNT; i++) {
        if (sPads[i].button & RT_SPRINT_BUTTON) {
            sPads[i].button |= SPRINT_BIT;
        }
    }
}

// Native libraries, such as Eltale's ambient sound, don't exist here.
u32 rt_native_stub(void) {
    return 0;
}
