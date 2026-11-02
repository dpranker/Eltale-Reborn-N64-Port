/* The runtime, linked by tools/link_mods.py after the mods. RT_BASE comes from the command line. Bss stays
   inside the loaded image, so nothing has to clear it. */
ENTRY(rt_native_stub)

SECTIONS {
    . = RT_BASE;
    .text : {
        *(.text*)
        *(.rodata*)
        *(.data*)
        *(.got*)
        . = ALIGN(8);
        *(.bss*)
        *(COMMON)
        . = ALIGN(16);
        rt_end = .;
    }
    /DISCARD/ : { *(.MIPS.*) *(.comment) *(.pdr) *(.mdebug*) *(.gnu*) *(.note*) *(.reginfo) *(.eh_frame*) }
}
