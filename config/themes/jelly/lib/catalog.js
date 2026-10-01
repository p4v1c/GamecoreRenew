/** Jelly's presentation of the real packs: photo, name, mark and colour.
 *
 * Nothing here is a game or a console list. The box says which packs exist
 * (`sdk.api.systems`), this only says how each one is dressed, keyed by its
 * pack id. A pack missing from the table still shows, with its pack logo and
 * the host's colour.
 */

// Jelly's eight cover colours, from the mockup.
const PINK = '#e2508f'
const ORANGE = '#d9783a'
const PURPLE = '#6a52b3'
const GREEN = '#2f8f74'
const BLUE = '#3f78bd'
const LILAC = '#8c6fc0'
const TEAL = '#24899c'
const CORAL = '#d4613f'

/** photo, full name, maker, year, short mark, cover colour. */
const CONSOLES = {
  duckstation: ['ps1.png', 'PlayStation', 'Sony', '1994', 'PS', PURPLE],
  pcsx2: ['ps2.png', 'PlayStation 2', 'Sony', '2000', 'PS2', BLUE],
  rpcs3: ['ps3.png', 'PlayStation 3', 'Sony', '2006', 'PS3', LILAC],
  shadps4: ['ps4.png', 'PlayStation 4', 'Sony', '2013', 'PS4', BLUE],
  ppsspp: ['psp.png', 'PlayStation Portable', 'Sony', '2004', 'PSP', TEAL],
  cemu: ['wiiu.png', 'Wii U', 'Nintendo', '2012', 'Wii U', TEAL],
  gamecube: ['gamecube.png', 'GameCube', 'Nintendo', '2001', 'GC', LILAC],
  wii: ['wii.png', 'Wii', 'Nintendo', '2006', 'Wii', BLUE],
  switch: ['switch.png', 'Nintendo Switch', 'Nintendo', '2017', 'Switch', CORAL],
  dolphin: ['gamecube.png', 'GameCube & Wii', 'Nintendo', '2001', 'GC', LILAC],
  ryujinx: ['switch.png', 'Nintendo Switch', 'Nintendo', '2017', 'Switch', CORAL],
  azahar: ['3ds.png', 'Nintendo 3DS', 'Nintendo', '2011', '3DS', PINK],
  melonds: ['ds.png', 'Nintendo DS', 'Nintendo', '2004', 'DS', TEAL],
  gb: ['gb.png', 'Game Boy', 'Nintendo', '1989', 'GB', GREEN],
  gbc: ['gbc.png', 'Game Boy Color', 'Nintendo', '1998', 'GBC', PINK],
  gba: ['gba.png', 'Game Boy Advance', 'Nintendo', '2001', 'GBA', GREEN],
  mgba: ['gba.png', 'Game Boy Advance', 'Nintendo', '2001', 'GBA', GREEN],
  gopher64: ['n64.png', 'Nintendo 64', 'Nintendo', '1996', 'N64', GREEN],
  rmg: ['n64.png', 'Nintendo 64', 'Nintendo', '1996', 'N64', GREEN],
  xenia: ['xbox360.png', 'Xbox 360', 'Microsoft', '2005', '360', GREEN],
  snes9x: ['snes.png', 'Super Nintendo', 'Nintendo', '1990', 'SNES', BLUE],
  nes: ['nes.png', 'NES', 'Nintendo', '1983', 'NES', CORAL],
  fds: ['fds.png', 'Famicom Disk System', 'Nintendo', '1986', 'FDS', ORANGE],
  mastersystem: ['mastersystem.png', 'Master System', 'Sega', '1985', 'SMS', BLUE],
  gamegear: ['gamegear.png', 'Game Gear', 'Sega', '1990', 'GG', TEAL],
  sg1000: ['sg1000.png', 'SG-1000', 'Sega', '1983', 'SG', BLUE],
  megadrive: ['megadrive.png', 'Mega Drive', 'Sega', '1988', 'MD', PURPLE],
  megacd: ['megacd.png', 'Mega-CD', 'Sega', '1991', 'MCD', TEAL],
  sega32x: ['32x.png', '32X', 'Sega', '1994', '32X', ORANGE],
  saturn: ['saturn.png', 'Saturn', 'Sega', '1994', 'SAT', LILAC],
  dreamcast: ['dreamcast.png', 'Dreamcast', 'Sega', '1998', 'DC', ORANGE],
  naomi: ['naomi.png', 'Naomi', 'Sega', '1998', 'NAOMI', TEAL],
  naomigd: ['naomi.png', 'Naomi GD-ROM', 'Sega', '2001', 'GD', TEAL],
  atomiswave: ['atomiswave.png', 'Atomiswave', 'Sammy', '2003', 'AW', CORAL],
  pcengine: ['pcengine.png', 'PC Engine', 'NEC', '1987', 'PCE', PINK],
  pcenginecd: ['pcenginecd.png', 'PC Engine CD', 'NEC', '1988', 'PCE CD', CORAL],
  supergrafx: ['supergrafx.png', 'SuperGrafx', 'NEC', '1989', 'SGX', ORANGE],
  mame: ['arcade.png', 'Arcade', 'MAME', '', 'ARC', ORANGE],
}

/** The application packs. Ids match catalog/<id>/pack.json. */
const APPS = {
  steam: {color: '#1f3b5c', category: 'Jeux PC', blurb: 'Steam en mode Big Picture, fait pour la manette.'},
  youtube: {color: '#c4302b', category: 'Vidéos', blurb: 'YouTube dans son interface TV.'},
  twitch: {color: '#7b45d6', category: 'En direct', blurb: 'Twitch avec EmberTV, l’interface TV du pack GameCore.'},
  stremio: {color: '#5b47c9', category: 'Films & séries', blurb: 'Stremio dans son interface TV.'},
}
const DEFAULT_APP = {color: PURPLE, category: 'Application', blurb: 'Une application de ton catalogue GameCore.'}

export const isApp = (s) => s?.kind === 'app' || s?.type === 'app' || s?.type === 'application'

const row = (s) => CONSOLES[s?.id] || null

export const systemName = (s) => isApp(s)
  ? (s?.label || s?.id || 'Application')
  : row(s)?.[1] || s?.platform || s?.label || s?.id || 'Console'
export const systemMark = (s) => row(s)?.[4] || String(s?.label || s?.id || '?').slice(0, 6)
export const systemMaker = (s) => row(s)?.[2] || ''
export const systemYear = (s) => row(s)?.[3] || ''
export const appStyle = (s) => APPS[s?.id] || DEFAULT_APP

/** The colour a console's covers sit on. The host's colour for an unknown pack. */
export const coverColor = (sdk, s) =>
  isApp(s) ? appStyle(s).color : row(s)?.[5] || (s && sdk.format.systemColor(s)) || PURPLE

export const packLogo = (s) => s?.iconPath
  ? `/assets/logos/${encodeURIComponent(s.iconPath.replace(/\\/g, '/').split('/').pop())}`
  : null

/** The console photo Jelly ships, else the pack's own logo. */
export const consoleArt = (sdk, s) => {
  const file = row(s)?.[0]
  return file ? sdk.system.asset(`assets/consoles/${file}`) : packLogo(s)
}

export const coverUrl = (systemId, filename) =>
  `/api/covers/${encodeURIComponent(systemId)}/${encodeURIComponent(filename)}`

/** `Zelda_(USA).iso` → `Zelda`, for a key that never went through the scanner.
 * Same two steps as backend/services/rom_scanner.py, then the host's gameName. */
export const titleFromKey = (sdk, key) => sdk.format.gameName(
  String(key || '').replace(/\.[^.]+$/, '').replace(/[([{][^)\]}]*[)\]}]/g, '').trim())

/** "1 jeu", "3 jeux". */
export const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`
