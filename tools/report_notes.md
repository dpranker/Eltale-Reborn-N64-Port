## Assessment

**Overall: go. Neither hook density nor the GBI scan changes the approach.** Relinking the binaries and patching the ROM looks workable for both mods. The scan did add required work, listed under "Changes the port needs".

This is static analysis only. Nothing has run in ares or on hardware yet, and frame rate is still unmeasured.

### Go/no-go by category

| Category | Verdict | Why | What to check |
|---|---|---|---|
| Story data | **Go** | About 400 KB of read-only data, plus most of the 405 KB of merged strings. All pointers have relocations. | Nothing specific |
| Script/event engine | **Go; speed unknown** | 58 KB of code, 7 entry and 18 return hooks, all mechanically clean. `camera_apply` emits an RT64 command. | Per-frame CPU in Phase 5 |
| Progression/economy/battle | **Go** | 34 KB of code plus the 16 KB gameplay mod. Hook-only changes to game logic. | 18 float-to-int sites in `battle`, 19 in `dodge` |
| Models | **Go, with fixes** | `bart_model_build` needs its address guards rewritten. Models built in mod memory depend on data-cache writeback. | Each custom and recolored model in ares |
| 2D/UI/FX | **Conditional** | The image loads with constant sizes look chunked, but several sizes come from registers. The image code also emits RT64 commands. | TMEM, fill rate and combiner on title, credits, license, JP HUD |
| Audio | **Go** | `ambience_*` become no-ops. Music hooks are ordinary hooks. | Music fades by ear |
| Debug | **Go** | `dev_scene`, `dev_force_crits` and `time_log` default to off. | Nothing specific |

### Hook surface

- 192 records on 100 game functions: 6 patches, 87 entry hooks, 99 return hooks.
- Entry hooks: all targets are at least 16 bytes, with no control flow in the first two instructions and no branch back into them. The engine won't need any relocated PC-relative instructions.
- Return hooks: every target has exactly one `jr ra` and no tail jumps. The other `jr` instructions in those targets are all jump tables.
- No hook or patch reads stack arguments, so the trampoline doesn't need to copy them. This replaces the plan's stack-argument copy; the build will re-run the check and fail if that changes.
- Overlays: 3 targets in `.ovl_title` and 3 in `.ovl_intro`, which patching ROM bytes handles.
- Threads: statically, no hook is reached from the audio, scheduler, PI or VI threads. 135 records are reached from game thread 6. The other 57 are reached only through function pointers, so their thread is still unknown.
- Hot functions: 5 hooked or patched targets are on the DC port's hot list (`func_800011DC`, `func_8000AC84`, `func_8000C4C4`, `func_80020F8C`, `func_8002B57C`). The floor probe isn't hooked.

### Changes the port needs

1. **RT64 commands must not reach the RSP.** The game runs F3DEX 1.23 (confirmed from the ROM's microcode string), and opcode `0x64` isn't an F3DEX command. RT64 is told to accept it through a magic word at 9 code sites, and the commands themselves appear at 11 sites in code plus one word in `world`'s read-only data. They are:
   - `G_EX_SETRDRAMEXTENDED` (`0x2C`), 10 code sites and the data word. It lets RT64 read mod memory above 8 MB, which isn't needed at 0x804xxxxx.
   - `G_EX_MATRIXGROUP` (`0xC`), 1 site in `camera_apply`. It groups matrices for RT64 interpolation.

   The proposed fix rewrites the `0x64` byte to `G_NOOP` (`0xC0`) at relink time, in each `lui` and in the data word. The enable magic has opcode `0x00`, which is F3DEX's `G_SPNOOP`, so it can stay. No feature is lost. How real F3DEX reacts to `0x64` wasn't tested and doesn't need to be.
2. **`bart_model_build` compares pointers with the old base.** 17 unrelocated constants (`0x81000000` and `0x80FFFFFF`) test whether a model's pointers are still in game memory. At 0x80400000 those tests would pass for mod pointers too. They must become `0x80400000` and `0x803FFFFF` in the relinker. The DC port relinks with the same constants, so its working build doesn't clear this; the effect there hasn't been traced.
3. **Data-cache writeback before graphics tasks.** `func_800011DC` writes back the game's 0xD0F0-byte display list pool, and `nnScExecuteAudio` writes back the whole cache before audio tasks. `nnScExecuteGraphics` doesn't write back anything beyond the task itself. Display lists, vertices and recolored textures in mod memory could be stale when the RSP or RDP reads them, which would show as flicker or corruption on real hardware. Whether ares shows it too is untested. The mods call no libultra cache functions. Proposed fix: call `osWritebackDCacheAll` from a hook before the graphics `osSpTaskLoad`, with its cost measured in Phase 5.
4. **Hook chains.** 10 functions are hooked by both mods, and Eltale patches `func_80016520`, which gameplay hooks. The engine has to run entry hooks, then the patch, then return hooks in reverse order.
5. **Hook context.** The PC runtime copies the entire register context before a hook and restores it after, and keeps a `thread_local` stack of contexts for `recomphook_get_return_*`. Trampolines must match: preserve argument and return registers including FP ones, and keep that value per thread and nest-safe.
6. **Float-to-int traps.** 78 sites (41 gameplay, 37 Eltale) can raise an exception on NaN or out-of-range input, where PC continues. Phase 3 and 4 runs need a breakpoint on the game's fault path.
7. **Config.** `button_names` defaults to `Dreamcast`, so dialogue would name the wrong buttons. The N64 build should use `Nintendo 64`. The other defaults can stay.

### Corrections to the brief

- **Mod size:** Eltale is 1.2 MB of image plus 103 KB of bss. Both mods together need about 1.32 MB, which leaves about 2.68 MB of the Expansion Pak's 4 MB.
- **Cross-mod imports and exports:** neither mod exports anything, so only `recomp_is_dependency_met` matters. The build should fail if an export ever appears.
- **Allocation:** neither mod imports an allocator, which confirms `NOTES.md`. No heap is needed.
- **Hook order:** PC order comes from the mod scan and the saved mod list, so it isn't strictly fixed. Alphabetical order and the DC port's list both put Eltale first. The plan uses Eltale first for entry hooks and gameplay first for return hooks, whichever way the images are linked. Phase 2 confirms the reversal by reading the runtime source.
- **Module sizes:** compared with the brief's table, story data is larger (about 800 KB with its strings, against ~480 KB). Script/event code is smaller (58 KB against ~85 KB). Models, 2D/UI, audio and debug are close. `ending`, `limelin_castle` and `main` weren't listed and are shown as Unlisted.
- **`0x807FFFFF` in the gameplay mod:** this is a "pointer below 8 MB" check, and it stays valid at 0x80400000. It's safe because the image stays under 8 MB. No change needed.

### Limits of this scan

- GBI words loaded from tables, or passed beyond the next call, can be missed. Phase 5 must still inspect actual display lists.
- Texture sizes taken from registers can't be judged statically. `sCreditArt` (124 KB), `sTitleLogo` (41 KB), `sCastleTex` (33 KB), `gJpMenuSheet` (17 KB) and `sLicenseNotice` (16 KB) all need checking in ares.
- The thread graph doesn't follow function pointers.
- Frame rate is the largest open risk. `PERFORMANCE.md` says the N64 runs below the DC port's 21.7 fps at Melrode's heaviest spot, without saying how that was measured. Eltale adds NPCs there, and below 30 fps the game runs in slow motion. Phase 5 needs a vanilla baseline at the same scenes.
- The game's display list pool is 0xD0F0 bytes, and mods add commands to it. Phase 5 should measure how full it gets, since anything past the pool isn't written back.
