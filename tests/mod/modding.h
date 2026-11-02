// The macros real mods are built with.
#ifndef MODDING_H
#define MODDING_H

#define RECOMP_IMPORT(mod, func) __attribute__((noinline, weak, used, section(".recomp_import." mod))) func { __builtin_trap(); }
#define RECOMP_PATCH __attribute__((section(".recomp_patch")))
#define RECOMP_HOOK(func) __attribute__((section(".recomp_hook." func)))
#define RECOMP_HOOK_RETURN(func) __attribute__((section(".recomp_hook_return." func)))

typedef unsigned int u32;
typedef int s32;
typedef unsigned short u16;

RECOMP_IMPORT("*", u32 recomp_get_config_u32(const char* key))
RECOMP_IMPORT("*", double recomp_get_config_double(const char* key))
RECOMP_IMPORT("*", s32 recomphook_get_return_s32(void))
RECOMP_IMPORT("*", u32 recomphook_get_return_u16(void))
RECOMP_IMPORT("*", u32 recomp_is_dependency_met(const char* id))
RECOMP_IMPORT("*", u32 recomp_get_smooth_transparency(void))
RECOMP_IMPORT("*", void recomp_printf(const char* format, ...))

// Results go to uncached free RAM at a fixed address, so gdb reads them with no symbols and no cache in the way.
#define RESULTS ((volatile u32*)0xA0700000)
#define LOG_COUNT RESULTS[0]
#define LOG_ENTRIES (&RESULTS[0x40])
#define LOG_MAX 32

static inline void log_event(u32 event) {
    if (LOG_COUNT < LOG_MAX) {
        LOG_ENTRIES[LOG_COUNT] = event;
        LOG_COUNT = LOG_COUNT + 1;
    }
}

// Game functions the tests call.
void dma_write(u32 rom, void* ram, u32 size);
u32 osGetCount(void);

#endif
