/**
 * What the home screen says about a console or an app, beyond its pack.
 *
 * A pack carries a label, a platform code and a brand colour, and that is all
 * `systems.list()` knows. The Studio home sets a console like a product page —
 * maker, year and kind above the name, a sentence under it — and none of that
 * exists on the box. Orbit already wrote it, keyed by pack id, in
 * `config/themes/orbit/lib/catalog.js`; the rows below are that table, reduced
 * to what this screen prints.
 *
 * Copied rather than imported on purpose. A theme can be removed, renamed or
 * replaced from Settings → Themes, and a Shelf that imported Orbit's file would
 * break the day Orbit changed shape or went away. No shipped theme imports
 * another (docs/themes/README.md §17 is the one sanctioned shared folder, and
 * it carries no data). If a row changes there, change it here.
 *
 * The only column Orbit does not have is the kind (handheld, arcade board,
 * add-on), which is plain fact about the hardware rather than copy.
 *
 * A pack missing from this table is not an error: the eyebrow and the sentence
 * are simply not drawn. Inventing a line for a console nobody described would
 * be the screen talking about something it does not know.
 */

/** [display name, maker, year(s), one line of copy], keyed by pack id. */
const CONSOLES = {
  duckstation: ['PlayStation', 'Sony', '1994',
    "Sony's first console, and the move to 3D on disc. Runs in DuckStation; needs its BIOS."],
  pcsx2: ['PlayStation 2', 'Sony', '2000',
    "Sony's DVD-era console. Runs in PCSX2; needs its BIOS."],
  rpcs3: ['PlayStation 3', 'Sony', '2006',
    'HD-era PlayStation, Blu-ray and all. Runs in RPCS3; needs its firmware.'],
  shadps4: ['PlayStation 4', 'Sony', '2013',
    'The current PlayStation generation. Runs in shadPS4; compatibility varies by game.'],
  ppsspp: ['PlayStation Portable', 'Sony', '2004',
    "Sony's first handheld, upscaled for the TV. Runs in PPSSPP."],
  cemu: ['Nintendo Wii U', 'Nintendo', '2012',
    'The GamePad console. Runs in Cemu; needs its keys.'],
  gamecube: ['GameCube', 'Nintendo', '2001 / 2002',
    "Nintendo's cube-shaped console, on mini discs. Runs in Dolphin."],
  wii: ['Wii', 'Nintendo', '2006',
    'The motion-controlled console and its Wii Remote. Runs in Dolphin.'],
  switch: ['Nintendo Switch', 'Nintendo', '2017',
    'The hybrid console, docked on your TV. Runs in Ryujinx; needs keys and firmware.'],
  dolphin: ['GameCube & Wii', 'Nintendo', '2001 / 2006',
    'GameCube and Wii discs in one emulator. Runs in Dolphin.'],
  ryujinx: ['Nintendo Switch', 'Nintendo', '2017',
    'The hybrid console, docked on your TV. Runs in Ryujinx; needs keys and firmware.'],
  azahar: ['Nintendo 3DS', 'Nintendo', '2011',
    'The 3D handheld with two screens. Runs in Azahar; L3 switches the layout.'],
  melonds: ['Nintendo DS', 'Nintendo', '2004',
    'The two-screen handheld with a touchscreen. Runs in melonDS; L3 switches the layout.'],
  gb: ['Game Boy', 'Nintendo', '1989 / 1990',
    'The original Game Boy, with its monochrome screen. Runs in mGBA.'],
  gbc: ['Game Boy Color', 'Nintendo', '1998',
    'The colour Game Boy, which also plays original Game Boy games. Runs in mGBA.'],
  gba: ['Game Boy Advance', 'Nintendo', '2001', 'The 32-bit pocket console. Runs in mGBA.'],
  mgba: ['Game Boy Advance', 'Nintendo', '2001', 'The 32-bit pocket console. Runs in mGBA.'],
  gopher64: ['Nintendo 64', 'Nintendo', '1996',
    "Four controller ports and the first 3D Mario. Runs in Rosalie's Mupen GUI."],
  rmg: ['Nintendo 64', 'Nintendo', '1996',
    "Four controller ports and the first 3D Mario. Runs in Rosalie's Mupen GUI."],
  xenia: ['Xbox 360', 'Microsoft', '2005',
    'The Xbox of the HD era. Runs in Xenia Canary; compatibility varies by game.'],
  lutris: ['PC', 'Windows', '',
    'Your PC games, run through Lutris and Wine without leaving the couch.'],
  snes9x: ['Super Nintendo', 'Nintendo', '1990 / 1992',
    'The 16-bit Nintendo, Mode 7 included. Runs in Snes9x.'],
  nes: ['NES', 'Nintendo', '1983 / 1986',
    'The 8-bit console that restarted home gaming. Runs in RetroArch.'],
  fds: ['Famicom Disk System', 'Nintendo', '1986',
    'The Famicom add-on that loaded games from disk. Japan only. Runs in RetroArch; needs its BIOS.'],
  mastersystem: ['Master System', 'Sega', '1985 / 1987', "Sega's 8-bit home console. Runs in RetroArch."],
  gamegear: ['Game Gear', 'Sega', '1990', "Sega's colour handheld. Runs in RetroArch."],
  sg1000: ['SG-1000', 'Sega', '1983', "Sega's first home console, from 1983. Runs in RetroArch."],
  megadrive: ['Mega Drive', 'Sega', '1988 / 1990',
    "Sega's 16-bit console, the Genesis in America. Runs in RetroArch."],
  megacd: ['Mega-CD', 'Sega', '1991 / 1993',
    'The CD add-on for the Mega Drive. Runs in RetroArch; needs its BIOS.'],
  sega32x: ['32X', 'Sega', '1994', 'The 32-bit add-on for the Mega Drive. Runs in RetroArch.'],
  saturn: ['Saturn', 'Sega', '1994 / 1995', "Sega's two-processor console. Runs in RetroArch; needs its BIOS."],
  dreamcast: ['Dreamcast', 'Sega', '1998 / 1999', "Sega's last console. Runs in RetroArch; needs its BIOS."],
  naomi: ['Naomi', 'Sega', '1998',
    'The arcade board related to the Dreamcast. Runs in RetroArch; needs its BIOS.'],
  naomigd: ['Naomi GD-ROM', 'Sega', '2001',
    'Naomi arcade games shipped on GD-ROM. Runs in RetroArch; needs its BIOS.'],
  atomiswave: ['Atomiswave', 'Sammy', '2003', "Sammy's cartridge arcade board. Runs in RetroArch; needs its BIOS."],
  pcengine: ['PC Engine', 'NEC', '1987 / 1989',
    "NEC's small console built for shooters, on HuCard. Runs in RetroArch."],
  pcenginecd: ['PC Engine CD', 'NEC', '1988 / 1989',
    'The PC Engine with a CD-ROM drive. Runs in RetroArch; needs its BIOS.'],
  supergrafx: ['SuperGrafx', 'NEC', '1989', 'An upgraded PC Engine with a handful of games. Runs in RetroArch.'],
  mame: ['Arcade', 'MAME', '', "Arcade machines, one ROM set per board. Runs in RetroArch's MAME core."],
}

/** The kind of hardware, for the eyebrow. Anything not listed is a home console. */
const KIND = {
  azahar: 'Handheld', melonds: 'Handheld', gb: 'Handheld', gbc: 'Handheld',
  gba: 'Handheld', mgba: 'Handheld', ppsspp: 'Handheld', gamegear: 'Handheld',
  switch: 'Hybrid', ryujinx: 'Hybrid', lutris: 'Computer',
  fds: 'Add-on', megacd: 'Add-on', sega32x: 'Add-on',
  naomi: 'Arcade board', naomigd: 'Arcade board', atomiswave: 'Arcade board', mame: 'Arcade',
}

/** The four application packs: who makes it, what it is for, one line. */
const APPS = {
  steam: ['Valve', 'PC games', 'Steam in Big Picture mode, made for a controller.'],
  youtube: ['Google', 'Video', 'YouTube’s TV interface.'],
  twitch: ['Twitch', 'Live', 'Twitch through EmberTV, the TV interface from the GameCore pack.'],
  stremio: ['Stremio', 'Movies & series', 'Stremio with its TV interface.'],
}

export const isApp = (s) => s?.kind === 'app' || s?.type === 'app' || s?.type === 'application'

/**
 * Everything the copy block prints about one tile, or null for a field
 * nobody wrote. `eyebrow` is already joined; an empty one is not drawn.
 */
export const describe = (s) => {
  if (!s) return { name: '', eyebrow: [], story: null }
  if (isApp(s)) {
    const row = APPS[s.id]
    return {
      name: s.label || s.id,
      eyebrow: row ? [row[0], row[1]] : [],
      story: row?.[2] || null,
    }
  }
  const row = CONSOLES[s.id]
  // "1990 / 1992" is Japan, then the West. The eyebrow carries one year, and
  // the first release is the one that dates the hardware.
  const year = row?.[2] ? row[2].split('/')[0].trim() : ''
  return {
    name: row?.[0] || s.label || s.platform || s.id,
    eyebrow: row ? [row[1], year, KIND[s.id] || 'Home console'].filter(Boolean) : [],
    story: row?.[3] || null,
  }
}

/** The short name under a photo in the bottom row: the pack's own platform code. */
export const shortName = (s) => (isApp(s) ? (s.label || s.id) : (s.platform || s.label || s.id))
