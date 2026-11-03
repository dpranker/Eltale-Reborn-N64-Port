# Builds from the vanilla ROM to a patched ROM. See PLAN.md for the phases.

ROM      := rom/quest64.us.z64
BUILD    := build
DUMP     := vendor/Eltale-Reborn/Quest64Syms/dump.toml

CC       := clang
LD       := ld.lld
OBJCOPY  := llvm-objcopy
PYTHON   := python3

# The same flags upstream uses for N64 patches. mips2 keeps registers to 32 bits, as the game expects.
CFLAGS   := -target mips -mips2 -mabi=32 -O2 -G0 -mno-abicalls -mno-odd-spreg -mno-check-zero-division \
            -fno-pic -ffreestanding -fno-builtin -fomit-frame-pointer -fno-stack-protector \
            -ffunction-sections -Wall -Wextra -Werror

LOADER_RAM_ADDR   := 0x80400000
LOADER_ROM_ADDR   := 0x1000000
LOADER_MAGIC_ADDR := 0x807FFFF0

# `make rom MODS=gameplay,eltale` writes build/rom/<mods>.z64. Eltale's hooks run first in a chain, as on PC
# and the Dreamcast port, whichever order the mods sit in memory.
comma    := ,
MODS     ?= gameplay,eltale
SETTINGS ?=
SPRINT   ?= L
ROM_DIR  := $(BUILD)/rom/$(subst $(comma),-,$(MODS))
NRM_gameplay := vendor/Eltale-Reborn-DC-Port/eltale/quest64_modern_gameplay.nrm
NRM_eltale   := vendor/Eltale-Reborn-DC-Port/eltale/eltale_reborn.nrm

.PHONY: phase1 test-phase1 phase2 test-phase2 test-rom-gameplay test-rom-vanilla test-rom-eltale test-phase3 test-phase4 perf-test-roms test-perf test-dl test-late perf-roms cart patch rom clean

phase1: $(BUILD)/phase1.z64

$(BUILD)/test_blob.bin: tools/gen_test_blob.py
	@mkdir -p $(BUILD)
	$(PYTHON) tools/gen_test_blob.py $@

$(BUILD)/game_syms.ld: tools/gen_game_syms.py $(DUMP)
	@mkdir -p $(BUILD)
	$(PYTHON) tools/gen_game_syms.py $(DUMP) $@

$(BUILD)/loader_config.h: $(BUILD)/test_blob.bin
	printf '#define LOADER_ROM_ADDR $(LOADER_ROM_ADDR)\n#define LOADER_RAM_ADDR $(LOADER_RAM_ADDR)\n#define LOADER_MAGIC_ADDR $(LOADER_MAGIC_ADDR)\n#define LOADER_SIZE %d\n' \
		$$(stat -c %s $<) > $@

$(BUILD)/loader.o: runtime/loader.c runtime/ultra.h $(BUILD)/loader_config.h
	$(CC) $(CFLAGS) -I$(BUILD) -c $< -o $@

$(BUILD)/stage1.elf: $(BUILD)/loader.o runtime/loader.ld $(BUILD)/game_syms.ld
	$(LD) -nostdlib -T $(BUILD)/game_syms.ld -T runtime/loader.ld -Map $(BUILD)/stage1.map $< -o $@

$(BUILD)/stage1.bin: $(BUILD)/stage1.elf
	$(OBJCOPY) -O binary -j .text $< $@

$(BUILD)/phase1.z64: tools/patch_rom.py tools/n64crc.py $(ROM) $(BUILD)/stage1.bin $(BUILD)/test_blob.bin
	$(PYTHON) tools/patch_rom.py --rom $(ROM) --stage1 $(BUILD)/stage1.bin --blob $(BUILD)/test_blob.bin --out $@

# The stage 1 addresses the gdb tests stop at.
$(BUILD)/phase1_syms.gdb: $(BUILD)/stage1.elf $(ROM)
	llvm-nm $< | awk '$$3 == "loader_halted" || $$3 == "loader_boot" { print "set $$" $$3 " = 0x" $$1 }' > $@
	$(PYTHON) -c "d=open('$(ROM)','rb').read(); print('set \$$title_word = (int)0x'+d[0xDA68F0+0x6D8:0xDA68F0+0x6DC].hex())" >> $@

test-phase1: phase1 $(BUILD)/phase1_syms.gdb $(BUILD)/vanilla.z64
	tests/run_phase1.sh

$(BUILD)/vanilla.z64: $(ROM)
	cp $< $@

# --- Phase 2: test mods, packaged the way real mods are ---

$(BUILD)/RecompModTool: tools/build_modtool.sh
	tools/build_modtool.sh $@

MOD_CFLAGS := $(filter-out -Wextra -Werror,$(CFLAGS)) -Wno-return-type -Itests/mod

# RecompModTool writes its files and then fails if zip isn't installed. link_mods.py reads the files.
$(BUILD)/phase2/%/mod_syms.bin: tests/mod/%.c tests/mod/%.toml tests/mod/modding.h tests/mod/results.h tests/mod/mod.ld $(BUILD)/RecompModTool
	@mkdir -p $(BUILD)/phase2/$*
	$(CC) $(MOD_CFLAGS) -c $< -o $(BUILD)/phase2/$*.o
	$(LD) -nostdlib --unresolved-symbols=ignore-all --emit-relocs -e 0 -T tests/mod/mod.ld -Map $(BUILD)/phase2/$*.map $(BUILD)/phase2/$*.o -o $(BUILD)/phase2/$*.elf
	-$(BUILD)/RecompModTool tests/mod/$*.toml $(BUILD)/phase2/$*/
	test -f $@

phase2: $(BUILD)/phase2/mod_a/mod_syms.bin $(BUILD)/phase2/mod_b/mod_syms.bin
	$(PYTHON) tools/build_rom.py --out $(BUILD)/phase2/rom --name phase2 --mod $(BUILD)/phase2/mod_a --mod $(BUILD)/phase2/mod_b \
		--set test_mod_a.sample_enum=Third

test-phase2: phase2 phase1 $(BUILD)/phase1_syms.gdb $(BUILD)/vanilla.z64
	$(PYTHON) tests/test_link_reject.py
	tests/run_phase2.sh

# The gameplay mod with test-only controller input, for the gdb scripts. Not for release.
test-rom-gameplay: $(BUILD)/phase2/input/mod_syms.bin
	$(PYTHON) tools/build_rom.py --out $(BUILD)/rom/gameplay-test --name gameplay-test --mod $(NRM_gameplay) --mod $(BUILD)/phase2/input \
		--sprint-button $(SPRINT) $(foreach s,$(SETTINGS),--set $(s))

# Both mods with test-only controller input.
test-rom-eltale: $(BUILD)/phase2/input/mod_syms.bin
	$(PYTHON) tools/build_rom.py --out $(BUILD)/rom/eltale-test --name eltale-test --hook-order eltale_reborn,quest64_modern_gameplay,test_input \
		--mod $(NRM_gameplay) --mod $(NRM_eltale) --mod $(BUILD)/phase2/input --sprint-button $(SPRINT) $(foreach s,$(SETTINGS),--set $(s))

test-rom-vanilla: $(BUILD)/phase2/input/mod_syms.bin
	$(PYTHON) tools/build_rom.py --out $(BUILD)/rom/vanilla-test --name vanilla-test --mod $(BUILD)/phase2/input

test-phase3: test-rom-vanilla test-rom-gameplay
	tests/run_phase3.sh

test-phase4: test-rom-eltale
	tests/run_phase4.sh

# The frame counter with test input, for tests/gdb/perf.py, and the same scenes on vanilla as the baseline.
perf-test-roms: $(BUILD)/phase2/input/mod_syms.bin $(BUILD)/phase2/perf/mod_syms.bin
	$(PYTHON) tools/build_rom.py --out $(BUILD)/rom/perf-vanilla-test --name perf-vanilla-test --mod $(BUILD)/phase2/input --mod $(BUILD)/phase2/perf
	$(PYTHON) tools/build_rom.py --out $(BUILD)/rom/perf-eltale-test --name perf-eltale-test --hook-order eltale_reborn,quest64_modern_gameplay,test_input,test_perf \
		--mod $(NRM_gameplay) --mod $(NRM_eltale) --mod $(BUILD)/phase2/input --mod $(BUILD)/phase2/perf --sprint-button $(SPRINT)

test-perf: perf-test-roms
	tests/run_perf.sh

# Checks real frames' display lists against what the hardware accepts, and estimates their pixel work.
test-dl: perf-test-roms
	tests/run_dl_check.sh

# The first boss and the mod's debug jumps, including the ending through the credits. Takes about 20 minutes.
test-late: perf-test-roms
	tests/run_late_game.sh

# Playable ROMs with the frame counter on screen, for consoles with no gdb. Not for release.
perf-roms: $(BUILD)/phase2/perf_hud/mod_syms.bin
	$(PYTHON) tools/build_rom.py --out $(BUILD)/rom/perf-vanilla --name perf-vanilla --mod $(BUILD)/phase2/perf_hud
	$(PYTHON) tools/build_rom.py --out $(BUILD)/rom/perf-eltale --name perf-eltale --hook-order eltale_reborn,quest64_modern_gameplay,test_perf_hud \
		--mod $(NRM_gameplay) --mod $(NRM_eltale) --mod $(BUILD)/phase2/perf_hud --sprint-button $(SPRINT)

# A BPS patch from the vanilla ROM to the real build. IPS can't address past 16 MB, where the mod image starts.
PATCH := $(BUILD)/patch/eltale-n64.bps

patch: rom
	@mkdir -p $(BUILD)/patch
	$(PYTHON) tools/make_bps.py --rom $(ROM) --target $(ROM_DIR)/$(subst $(comma),-,$(MODS)).z64 --out $(PATCH)
	$(PYTHON) tests/test_bps.py $(ROM) $(ROM_DIR)/$(subst $(comma),-,$(MODS)).z64 $(PATCH)

# Copies the real ROM and both counter ROMs to the SummerCart64's SD card. Keep the console off while this runs.
SC64        := .tools/sc64/sc64deployer
CART_DIR    := /N64/Eltale
CART_ROMS   := gameplay-eltale:eltale perf-eltale:perf-eltale perf-vanilla:perf-vanilla

cart:
	@$(SC64) sd stat $(CART_DIR) > /dev/null 2>&1 || $(SC64) sd mkdir $(CART_DIR)
	@for r in $(CART_ROMS); do $(SC64) sd upload $(BUILD)/rom/$${r%%:*}/$${r%%:*}.z64 $(CART_DIR)/$${r##*:}.z64 || exit 1; done
	@$(SC64) sd ls $(CART_DIR)

rom:
	$(PYTHON) tools/build_rom.py --out $(ROM_DIR) --name $(subst $(comma),-,$(MODS)) --hook-order $(if $(findstring eltale,$(MODS)),$(if $(findstring gameplay,$(MODS)),eltale_reborn$(comma)quest64_modern_gameplay,eltale_reborn),quest64_modern_gameplay) \
		--sprint-button $(SPRINT) $(foreach m,$(subst $(comma), ,$(MODS)),--mod $(NRM_$(m))) $(foreach s,$(SETTINGS),--set $(s))

clean:
	rm -rf $(BUILD)
