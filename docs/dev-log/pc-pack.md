# PC games (Lutris pack): dev log

## Status

Groundwork merged. The pack itself is not written yet; this is the plan.

## Done (groundwork)

- **Shelf, the PC case** (`config/themes/shelf/views/pc-case.js`, `css/pc-case.css`,
  `lib/pc.js`). A system whose pack id is in `lib/pc.js` (`lutris`, `pc`) is drawn
  in the PC template the owner approved:
  - a blue band (`--pc: #2F5BEA`) with a monitor glyph and "PC" across the front;
  - white plastic for the hinge edge, the ends and the spine (spine head blue, "PC");
  - a printed reverse when there is no `box-back` scan: band, key art under the
    clear logo, blurb, two shots, minimum spec panel, credit line, bars;
  - a disc on the card instead of a cartridge, "PC" instead of the extension stamp.
- **Media for the reverse**: `clear-logo(-hd)`, `fanart-background` (key art,
  falls back to `screenshot-gameplay`), `screenshot-gameplay`, `screenshot-game-title`.
- **`GameMeta.requirements`** (`backend/services/gamemedia/__init__.py`
  `to_game_meta`): `{os, cpu, ram, gpu, disk}`, empty for consoles. A PC source
  fills `manifest.meta.requirements`; the reverse prints only the rows present.
- **Console copy**: `lutris` rows in Shelf `lib/consoles.js` (kind "Computer"),
  Orbit `lib/catalog.js`, Jelly `lib/catalog.js`.

## To do in the pack

1. `catalog/lutris/`: pack.json (id `lutris`, label "PC", platform "PC"), the
   monitor logo in `pc-pack-tools/logo.png` as `catalog/lutris/logo.png`.
2. Library: read the Lutris library (`lutris -l -j` or its `pga.db`), one entry
   per installed game; covers from Lutris's own `coverart/` as a first source.
3. Launch: `lutris lutris:rungameid/<id>` with no Lutris window; session ends
   when the game's process tree exits.
4. Media source for PC: ScreenScraper by name (system "PC Windows"); fill
   `meta.requirements` from a PC source (Steam store data or PCGamingWiki).
5. Hide the extension badge for PC in the host library (Summer and default show
   the ext under each title).
6. Jelly: a drawn 3D box fallback when there is no `box-3d` (PC games rarely have one).

## Checking it without a pack

`pc-pack-tools/pc-shots.cjs` drives devserve with a fake `lutris` system and
answers `/api/media/lutris/*` itself from a `pcmock/` folder (data.json with
blurb, developer, year, genres, reqs, shots, logo), the shape a PC source will
return. Usage at the top of the file; the fake system is a `lutris` entry in
`$GAMECORE_DATA/config/systems.json` with empty `*.lutris` files and covers in
`emu/covers/lutris/`.
