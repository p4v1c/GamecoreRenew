# Launch cover — the "game is running" signals, measured — 2026-10-25

Read-only, on the reference box: the logs the emulators had already written
during real play. Nothing was launched for this report.

## RPCS3 — `@FLATPAK_CACHE@/rpcs3/RPCS3.log`

One log per boot: the previous one is compressed aside and a new
`RPCS3.log` written. A FIFA 19 boot, warm caches:

| t | line | on screen |
|---|---|---|
| 1.27 s | `GUI: gui_application: Creating new game window` | black window |
| 3.22 s | `{RSX Worker n} RSX: ...` (pipeline cache) | "Loading pipeline objects" |
| 3.50–12.2 s | `{PPU[0x1000000] main_thread} PPU: ...` (analysis, LLVM modules) | PPU compile dialog |
| 12.45–28.99 s | `SPU: Building function ...`, then `SPU Runtime: Built 27555 functions.` | SPU cache dialog |
| 29.00 s | `{PPU[0x1000000] Thread (main_thread) [liblv2: …]} sys_memory: …` | the game's own boot |

Before 29 s the main thread logs as `{PPU[..] main_thread}`; from the first
call the game's own code makes, as `{PPU[..] Thread (main_thread) [<module>: <addr>]}`.
Signal: `Thread \(main_thread\) \[`. Ceiling 240 s: a cold PPU/SPU cache takes
minutes, and past it the player sees RPCS3's progress, which is information.
Not covered: the native build (`preferIfPresent`, `~/.cache/rpcs3`), unused on
the reference box.

## Ryujinx — `@FLATPAK_CONFIG@/Ryujinx/Logs/Ryujinx_*.log`

A new file per run. Three runs (Mario Party Jamboree ×2, Mario Kart 8 Deluxe):

| run | `Shader cache loaded.` | PTC `MakeAndSaveTranslations … translated in` | `SurfaceFlinger CreateLayerFromId` |
|---|---|---|---|
| 2026-10-09 | 2.28 s | 11.56 s | 12.08 s |
| 2026-10-10 | 2.70 s | 6.65 s | 7.17 s |
| 2026-10-24 | 1.41 s (0 shaders) | — | 4.76 s |

`Shader cache loaded.` comes before the PTC pass, which Ryujinx also shows a
loading screen for. The game creating its display layer comes after both, in
all three. Signal: `SurfaceFlinger CreateLayerFromId`. Ceiling 180 s.

## PCSX2 and Dolphin — no usable log

- PCSX2's `logs/emulog.txt` is buffered: the last run's file stops at 1.77 s,
  during GS init. Window rule, WM_CLASS from the desktop file
  (`StartupWMClass=pcsx2-qt`) and the bezel config. Ceiling 30 s.
- Dolphin writes no log (`Logger.ini` `WriteToFile = False`) and compiles
  shaders asynchronously (`GFX.ini` `ShaderCompilationMode = 2`), so it shows
  no loading screen of its own. Window rule on `dolphin-emu`; no
  `StartupWMClass` in its desktop file, so the class is Qt's default (the
  binary's name). Ceiling 30 s.

Both are to be confirmed on the TV: a wrong class costs a cover held over the
game until the ceiling.

## Not covered

Retro packs start their game in well under a second: a cover would only flash.
Native ports declare their own signal (`# gamecore-ready-*`); Uncharted's
`Saves/last_run.log` prints `Entering original x86-64 code` once the game runs.
