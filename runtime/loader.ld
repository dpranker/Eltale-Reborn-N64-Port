/* Stage 1 goes over func_800471B0, which is 0x6A4 bytes. */
ENTRY(loader_boot)

SECTIONS {
    . = 0x800471B0;
    .text : {
        *(.text.loader_boot)
        *(.text*)
        *(.rodata*)
        *(.data*)
        *(.got*)
    }
    .bss : { *(.bss*) *(COMMON) }
    /DISCARD/ : { *(.MIPS.*) *(.comment) *(.pdr) *(.mdebug*) *(.gnu*) *(.note*) *(.reginfo) *(.eh_frame*) }
    ASSERT(. <= 0x800471B0 + 0x6A4, "stage 1 doesn't fit in func_800471B0")
    ASSERT(SIZEOF(.bss) == 0, "stage 1 can't have bss: nothing would clear it")
}
