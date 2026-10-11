# BIOS coverage per pack — 2026-10-11

Which packs need a file the owner supplies, and why each one has, or has no,
`bios` block in its `pack.json`. The `bios-manager` addon files uploads by
reading `GET /api/bios`, so a pack without a block is a system it cannot serve.

## Decisions

| Pack | Needs | Block | Evidence |
|---|---|---|---|
| `mame` | optional, per board family (`neogeo.zip`, `qsound.zip`, `pgm.zip`…) | **added** `system/mame/bios/*.zip` | libretro MAME rompath = `<rom dir>;<system>/mame/bios;<system>/mame/roms` (`src/osd/libretro/libretro-internal/retro_init.cpp`); system dir set by `scripts/gamecore-retroarch-launch.py`. Not the ROM folder: a BIOS zip there shows as a game tile |
| `shadps4` | optional system modules | **added** `@FLATPAK_DATA@/shadPS4/sys_modules/*.sprx` | user dir = `$XDG_DATA_HOME/shadPS4` (`src/common/path_util.cpp`); LLE allow-list `ModulesToLoad` in `src/core/libraries/sysmodule/sysmodule_internal.cpp`; a missing module is emulated or stubbed |
| `gamecube` | optional IPL per region | **added** `@FLATPAK_DATA@/dolphin-emu/GC/<EUR,USA,JAP>/IPL.bin` | Dolphin HLE-boots without it; Flatpak-only pack, fixed path |
| `sega32x` | none | none | PicoDrive's libretro port loads only Mega-CD BIOS (`find_bios` in `platform/libretro/libretro.c`); `pico/32x/32x.c` uses its built-in 32X BIOS when none is loaded |
| `gba`, `gb`, `gbc` | optional | none, kept in the addon | `preferIfPresent: /usr/bin/mgba-qt` makes the folder `~/.config/mgba` or the Flatpak one depending on the box; `bios.dir` holds one path |
| `melonds` | optional for DS, required for DSi | none, kept in the addon | paths are whatever the owner set in `melonDS.toml`; no fixed directory |
| `wii` | none | none | Dolphin creates the NAND |
| `ppsspp`, `xenia`, `gopher64`, `snes9x` | none | none | HLE kernels / no boot ROM |
| `azahar` | none | none | system files come from the Artic Setup Tool, not a file |
| `nes`, `megadrive`, `mastersystem`, `gamegear`, `sg1000`, `pcengine`, `supergrafx` | none | none | cartridge systems; Genesis Plus GX's boot-ROM option defaults off |
| `dolphin`, `mgba` | — | none | superseded packs, kept for old tiles |
| `lutris`, `steam`, apps | — | none | not emulators of a console |

Already declared before this session: `atomiswave`, `cemu`, `dreamcast`,
`duckstation`, `fds`, `megacd`, `naomi`, `naomigd`, `pcenginecd`, `pcsx2`,
`rpcs3`, `ryujinx`, `saturn`, `switch`.

No schema change: a MAME set is a `file` without `md5` (sets vary by MAME
version, like `dc/naomi.zip`), and a module folder is a `file` with a
subdirectory.

## Not done

- The addon recognises declared `.zip` names only; `.sprx` uploads need its
  `server.py` filter widened (tracked in the addon repo).
