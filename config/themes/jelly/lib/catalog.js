/** How each real pack is dressed: name, mark, colour, keyed by pack id. The box
 * says which packs exist and which pictures each ships (`system.art`); a pack
 * missing here still shows, with its logo and the host's colour. */

// Jelly's eight cover colours, from the mockup.
const PINK = '#e2508f'
const ORANGE = '#d9783a'
const PURPLE = '#6a52b3'
const GREEN = '#2f8f74'
const BLUE = '#3f78bd'
const LILAC = '#8c6fc0'
const TEAL = '#24899c'
const CORAL = '#d4613f'

/** full name, maker, year, short mark, cover colour. */
const CONSOLES = {
  duckstation: ['PlayStation', 'Sony', '1994', 'PS', PURPLE],
  pcsx2: ['PlayStation 2', 'Sony', '2000', 'PS2', BLUE],
  rpcs3: ['PlayStation 3', 'Sony', '2006', 'PS3', LILAC],
  shadps4: ['PlayStation 4', 'Sony', '2013', 'PS4', BLUE],
  ppsspp: ['PlayStation Portable', 'Sony', '2004', 'PSP', TEAL],
  cemu: ['Wii U', 'Nintendo', '2012', 'Wii U', TEAL],
  gamecube: ['GameCube', 'Nintendo', '2001', 'GC', LILAC],
  wii: ['Wii', 'Nintendo', '2006', 'Wii', BLUE],
  switch: ['Nintendo Switch', 'Nintendo', '2017', 'Switch', CORAL],
  dolphin: ['GameCube & Wii', 'Nintendo', '2001', 'GC', LILAC],
  ryujinx: ['Nintendo Switch', 'Nintendo', '2017', 'Switch', CORAL],
  azahar: ['Nintendo 3DS', 'Nintendo', '2011', '3DS', PINK],
  melonds: ['Nintendo DS', 'Nintendo', '2004', 'DS', TEAL],
  gb: ['Game Boy', 'Nintendo', '1989', 'GB', GREEN],
  gbc: ['Game Boy Color', 'Nintendo', '1998', 'GBC', PINK],
  gba: ['Game Boy Advance', 'Nintendo', '2001', 'GBA', GREEN],
  mgba: ['Game Boy Advance', 'Nintendo', '2001', 'GBA', GREEN],
  gopher64: ['Nintendo 64', 'Nintendo', '1996', 'N64', GREEN],
  rmg: ['Nintendo 64', 'Nintendo', '1996', 'N64', GREEN],
  xenia: ['Xbox 360', 'Microsoft', '2005', '360', GREEN],
  lutris: ['PC', 'Windows', '', 'PC', BLUE],
  snes9x: ['Super Nintendo', 'Nintendo', '1990', 'SNES', BLUE],
  nes: ['NES', 'Nintendo', '1983', 'NES', CORAL],
  fds: ['Famicom Disk System', 'Nintendo', '1986', 'FDS', ORANGE],
  mastersystem: ['Master System', 'Sega', '1985', 'SMS', BLUE],
  gamegear: ['Game Gear', 'Sega', '1990', 'GG', TEAL],
  sg1000: ['SG-1000', 'Sega', '1983', 'SG', BLUE],
  megadrive: ['Mega Drive', 'Sega', '1988', 'MD', PURPLE],
  megacd: ['Mega-CD', 'Sega', '1991', 'MCD', TEAL],
  sega32x: ['32X', 'Sega', '1994', '32X', ORANGE],
  saturn: ['Saturn', 'Sega', '1994', 'SAT', LILAC],
  dreamcast: ['Dreamcast', 'Sega', '1998', 'DC', ORANGE],
  naomi: ['Naomi', 'Sega', '1998', 'NAOMI', TEAL],
  naomigd: ['Naomi GD-ROM', 'Sega', '2001', 'GD', TEAL],
  atomiswave: ['Atomiswave', 'Sammy', '2003', 'AW', CORAL],
  pcengine: ['PC Engine', 'NEC', '1987', 'PCE', PINK],
  pcenginecd: ['PC Engine CD', 'NEC', '1988', 'PCE CD', CORAL],
  supergrafx: ['SuperGrafx', 'NEC', '1989', 'SGX', ORANGE],
  mame: ['Arcade', 'MAME', '', 'ARC', ORANGE],
}

/** The application packs. Ids match catalog/<id>/pack.json. */
const APPS = {
  steam: {color: '#1f3b5c', category: 'PC games', blurb: 'Steam in Big Picture mode, built for the pad.'},
  youtube: {color: '#c4302b', category: 'Videos', blurb: 'YouTube in its TV interface.'},
  twitch: {color: '#7b45d6', category: 'Live', blurb: 'Twitch through EmberTV, the TV interface in the GameCore pack.'},
  stremio: {color: '#5b47c9', category: 'Films & series', blurb: 'Stremio in its TV interface.'},
}
const DEFAULT_APP = {color: PURPLE, category: 'Application', blurb: 'An app from your GameCore catalogue.'}

export const isApp = (s) => s?.kind === 'app' || s?.type === 'app' || s?.type === 'application'

const row = (s) => CONSOLES[s?.id] || null

export const systemName = (s) => isApp(s)
  ? (s?.label || s?.id || 'Application')
  : row(s)?.[0] || s?.platform || s?.label || s?.id || 'Console'
export const systemMark = (s) => row(s)?.[3] || String(s?.label || s?.id || '?').slice(0, 6)
export const systemMaker = (s) => row(s)?.[1] || ''
export const systemYear = (s) => row(s)?.[2] || ''
export const appStyle = (s) => APPS[s?.id] || DEFAULT_APP

/** The colour a console's covers sit on. The host's colour for an unknown pack. */
export const coverColor = (sdk, s) =>
  isApp(s) ? appStyle(s).color : row(s)?.[4] || (s && sdk.format.systemColor(s)) || PURPLE

export const packLogo = (s) => s?.iconPath
  ? `/assets/logos/${encodeURIComponent(s.iconPath.replace(/\\/g, '/').split('/').pop())}`
  : null

/** The pack's console photo (catalog/<id>/art/console.*), else its logo.
 * Changing the photo is changing that file; Jelly holds no copy. */
// Tiles older boxes still carry for a pack that no longer exists: the photo is
// its successor's, served by that pack.
const SUCCESSOR = {rmg: 'gopher64'}
export const consoleArt = (sdk, s) => s?.art?.console
  || (SUCCESSOR[s?.id] && `/api/systems/${SUCCESSOR[s.id]}/art/console`)
  || packLogo(s)

export const coverUrl = (systemId, filename) =>
  `/api/covers/${encodeURIComponent(systemId)}/${encodeURIComponent(filename)}`

/** `Zelda_(USA).iso` → `Zelda`, for a key that never went through the scanner.
 * Same two steps as backend/services/rom_scanner.py, then the host's gameName. */
export const titleFromKey = (sdk, key) => sdk.format.gameName(
  String(key || '').replace(/\.[^.]+$/, '').replace(/[([{][^)\]}]*[)\]}]/g, '').trim())

/** "0 games", "1 game", "3 games". */
export const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`
