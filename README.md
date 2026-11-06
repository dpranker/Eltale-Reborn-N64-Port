# Eltale Reborn: Holy Magic Century - N64 version

Eltale Reborn: Holy Magic Century is a full reimagining of Quest 64, combining the N64 and GBC versions of the game as inspiration for an all new version that aims to deliver a satisfying and fresh RPG experience.

This repository builds a version of [Eltale Reborn](https://github.com/billymonks/Eltale-Reborn) and Quest 64: Modern Gameplay that runs on a real Nintendo 64. It takes the same compiled mods as the PC version and patches them into the original ROM.

This version was made in cooperation with [billymonks](https://github.com/billymonks). The hard work is his: Eltale Reborn and Modern Gameplay are his creations, and this repository only makes them run on N64 hardware.

Eltale Reborn is an independent, noncommercial fan modification. Not affiliated with or endorsed by Imagineer, SEGA, Nintendo, THQ, or Konami.

Original game © 1998 Imagineer Co., Ltd.

The PC version is https://github.com/billymonks/Eltale-Reborn. The Dreamcast version is https://github.com/billymonks/Eltale-Reborn-DC-Port.

## Requirements

- A Nintendo 64 with an **Expansion Pak**, or an emulator or clone console that provides 8 MB. The mods live in the Expansion Pak's memory.
- A **Controller Pak** for saves.
- A flash cart to run the patched ROM.

Tested with a SummerCart64 on a real Nintendo 64 and on an Analogue 3D, and in ares.

The game drops frames in some busy scenes on stock hardware, as the original Quest 64 does. On an Analogue 3D, overclocking smooths these out well.

## Patch

Apply `eltale-reborn-n64-<version>.bps` to your own Quest 64 (USA) 1.0 ROM with any BPS patcher, such as [Flips](https://github.com/Alcaro/Flips) or [ROM Patcher JS](https://www.marcrobledo.com/RomPatcher.js/). The ROM must be big-endian `.z64` with this SHA-1:

```
91b96e938c6d91699057fad91d726ee5a23ce33a
```

Don't distribute the ROM or the patched ROM.

## Build

Needs `make`, Python 3.11 or newer, and LLVM (`clang`, `ld.lld`, `llvm-objcopy`).

```
git clone --recurse-submodules https://github.com/dpranker/Eltale-Reborn-N64-Port
cd Eltale-Reborn-N64-Port
```

Put your ROM at `rom/quest64.us.z64`, then:

| Command | Writes |
| --- | --- |
| `make rom` | `build/rom/gameplay-eltale/gameplay-eltale.z64` |
| `make patch` | The ROM, then `build/patch/eltale-reborn-n64-<version>.bps`, checked by applying it again |

The mods come from the `vendor/Eltale-Reborn` submodule at the version's tag.

## Controls

The controls are the game's own, plus Modern Gameplay's sprint:

| Button | Action |
| --- | --- |
| D-Pad Up | Sprint on or off, in the field and in battle |

To use another button, build with `make rom SPRINT=<button>`: `D-UP`, `D-DOWN`, `D-LEFT`, `D-RIGHT`, `L`, `R`, `Z`, or a C button (`C-UP` and so on). L moves the field camera, so it's not the default.

## Options

The PC version has an in-game menu for the mods' options. On N64 they're fixed when the ROM is built, at the mods' defaults. To change one, build with `make rom SETTINGS="mod.option=value ..."`, for example:

```
make rom SETTINGS="quest64_modern_gameplay.hold_to_pass=Off"
```

The option names are in each mod's `mod.json`, inside its `.nrm`.

## Saves

Saves go to the Controller Pak, as in the original game.

## How it works

- A small loader sits in place of 64DD library code the game never runs. At boot, it copies the mods into the Expansion Pak's memory at 0x80400000.
- The mods are relocated from their PC address (0x81000000). Their hooks into the game become jumps to small trampolines.
- RT64-only display list commands become no-ops, since the N64's microcode doesn't have them.
- Each mod version is checked against the words the build patches, so a new version can't build with a wrong patch.

## Credits

- Eltale Reborn and Quest 64: Modern Gameplay by Billy Monks.
- [Quest 64: Recompiled](https://github.com/Rainchus/Quest64-Recomp) and its symbols.
- [N64Recomp](https://github.com/N64Recomp/N64Recomp), for the mod format.
- The Dreamcast version, for its mod file parsers.

## License

GPL-3.0, same as Quest 64: Recompiled and the Dreamcast version. See [COPYING](COPYING).
