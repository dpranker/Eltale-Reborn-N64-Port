/* Links a test mod at the address real mods use. RecompModTool reads the sections by name. */
SECTIONS {
    . = 0x81000000;
    .rodata : { *(.rodata*) }
    .data : { *(.data*) }
    .bss : { *(.bss*) *(COMMON) }
    /DISCARD/ : { *(.MIPS.*) *(.comment) *(.pdr) *(.mdebug*) *(.gnu*) *(.note*) *(.reginfo) *(.eh_frame*) }
}
