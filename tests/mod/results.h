// Slots in RESULTS, shared by the test mods. tests/gdb/phase2.gdb has the same numbers.
#define R_FIRST_DMA_ROM 1
#define R_FIRST_DMA_RAM 2
#define R_FIRST_DMA_SIZE 3
#define R_DMA_ENTRY_HITS 4
#define R_DMA_RETURN_HITS 5
#define R_FLOAT_ARG 6
#define R_FLOAT_ARG_B 7
#define R_FLOAT_RESULT 8
#define R_FLOAT_RESULT_B 9
#define R_FLOAT_HITS 10
#define R_COUNT_RETURN 11
#define R_COUNT_SEEN_BY_HOOK 12
#define R_NEST_BEFORE 13
#define R_NEST_INNER 14
#define R_NEST_AFTER 15
#define R_PATCH_HITS 16
#define R_TITLE_OVERLAY_HITS 17
#define R_CONFIG_U32 18
#define R_CONFIG_ENUM 19
#define R_CONFIG_DOUBLE_X100 20
#define R_DEP_FOUND 21
#define R_DEP_MISSING 22
#define R_SMOOTH 23
#define R_NATIVE 24
#define R_ARGS_B 25
#define R_U16 26
#define R_DELAY_SLOT_OK 27
#define R_DELAY_SLOT_BAD 28

// Events in the order log, for the patched function's chain.
#define EV_A_PATCH 0xA0
#define EV_B_ENTRY 0xB1
#define EV_B_RETURN 0xB2
#define EV_A_DMA_ENTRY 0xA3
#define EV_B_DMA_ENTRY 0xB3
#define EV_A_DMA_RETURN 0xA4
#define EV_B_DMA_RETURN 0xB4
