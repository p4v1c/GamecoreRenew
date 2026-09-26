/** Orbit's presentation data, and the real packs it dresses.
 *
 * The mockup carried its own `games` and `systems` arrays — twelve invented
 * titles and thirteen consoles with hand-written copy. None of that survives
 * here: a theme that shipped its own game list would be showing the player a
 * library they do not own. What survives is the PRESENTATION — the maker, the
 * year, the accent, the sentence under the console name — keyed by the real
 * pack id, so a box with three emulators shows three consoles and a box with
 * thirteen shows thirteen.
 */

/** file, display name, maker, year, accent, short mark, and the line of copy. */
export const consoles = {
  duckstation: ['ps1.png', 'PlayStation', 'Sony', '1994', '#8d9aff', 'PS',
    "Sony's first console, and the move to 3D on disc. Runs in DuckStation; needs its BIOS."],
  pcsx2: ['ps2.png', 'PlayStation 2', 'Sony', '2000', '#749dff', 'PS2',
    "Sony's DVD-era console. Runs in PCSX2; needs its BIOS."],
  rpcs3: ['ps3.png', 'PlayStation 3', 'Sony', '2006', '#b59afa', 'PS3',
    'HD-era PlayStation, Blu-ray and all. Runs in RPCS3; needs its firmware.'],
  shadps4: ['ps4.png', 'PlayStation 4', 'Sony', '2013', '#5cafff', 'PS4',
    'The current PlayStation generation. Runs in shadPS4; compatibility varies by game.'],
  ppsspp: ['psp.png', 'PlayStation Portable', 'Sony', '2004', '#9cacf2', 'PSP',
    "Sony's first handheld, upscaled for the TV. Runs in PPSSPP."],
  cemu: ['wiiu.png', 'Nintendo Wii U', 'Nintendo', '2012', '#6cdae9', 'Wii U',
    'The GamePad console. Runs in Cemu; needs its keys.'],
  dolphin: ['gamecube.png', 'GameCube & Wii', 'Nintendo', '2001 / 2006', '#ae91f5', 'GC',
    'GameCube and Wii discs in one emulator. Runs in Dolphin.'],
  ryujinx: ['switch.png', 'Nintendo Switch', 'Nintendo', '2017', '#ff8292', 'Switch',
    'The hybrid console, docked on your TV. Runs in Ryujinx; needs keys and firmware.'],
  azahar: ['3ds.png', 'Nintendo 3DS', 'Nintendo', '2011', '#93cde9', '3DS',
    'The 3D handheld with two screens. Runs in Azahar; L3 switches the layout.'],
  melonds: ['ds.png', 'Nintendo DS', 'Nintendo', '2004', '#b9c7ef', 'DS',
    'The two-screen handheld with a touchscreen. Runs in melonDS; L3 switches the layout.'],
  mgba: ['gba.png', 'Game Boy Advance', 'Nintendo', '2001', '#aa97e8', 'GBA',
    'The 32-bit pocket console. Runs in mGBA.'],
  gopher64: ['n64.png', 'Nintendo 64', 'Nintendo', '1996', '#7cd0a0', 'N64',
    "Four controller ports and the first 3D Mario. Runs in Rosalie's Mupen GUI."],
  rmg: ['n64.png', 'Nintendo 64', 'Nintendo', '1996', '#7cd0a0', 'N64',
    "Four controller ports and the first 3D Mario. Runs in Rosalie's Mupen GUI."],
  xenia: ['xbox360.png', 'Xbox 360', 'Microsoft', '2005', '#a5d998', '360',
    'The Xbox of the HD era. Runs in Xenia Canary; compatibility varies by game.'],
  snes9x: ['snes.png', 'Super Nintendo', 'Nintendo', '1990 / 1992', '#b6a4ff', 'SNES',
    'The 16-bit Nintendo, Mode 7 included. Runs in Snes9x.'],
  nes: ['nes.png', 'NES', 'Nintendo', '1983 / 1986', '#ff9a9a', 'NES',
    'The 8-bit console that restarted home gaming. Runs in RetroArch.'],
  fds: ['fds.png', 'Famicom Disk System', 'Nintendo', '1986', '#ffab8a', 'FDS',
    'The Famicom add-on that loaded games from disk. Japan only. Runs in RetroArch; needs its BIOS.'],
  mastersystem: ['mastersystem.png', 'Master System', 'Sega', '1985 / 1987', '#8fb8ff', 'SMS',
    "Sega's 8-bit home console. Runs in RetroArch."],
  gamegear: ['gamegear.png', 'Game Gear', 'Sega', '1990', '#a9bccd', 'GG',
    "Sega's colour handheld. Runs in RetroArch."],
  sg1000: ['sg1000.png', 'SG-1000', 'Sega', '1983', '#8fd0ff', 'SG',
    "Sega's first home console, from 1983. Runs in RetroArch."],
  megadrive: ['megadrive.png', 'Mega Drive', 'Sega', '1988 / 1990', '#aab4ff', 'MD',
    "Sega's 16-bit console, the Genesis in America. Runs in RetroArch."],
  megacd: ['megacd.png', 'Mega-CD', 'Sega', '1991 / 1993', '#9ec3d6', 'MCD',
    'The CD add-on for the Mega Drive. Runs in RetroArch; needs its BIOS.'],
  sega32x: ['32x.png', '32X', 'Sega', '1994', '#ffb07a', '32X',
    'The 32-bit add-on for the Mega Drive. Runs in RetroArch.'],
  saturn: ['saturn.png', 'Saturn', 'Sega', '1994 / 1995', '#b9c2ce', 'SAT',
    "Sega's two-processor console. Runs in RetroArch; needs its BIOS."],
  dreamcast: ['dreamcast.png', 'Dreamcast', 'Sega', '1998 / 1999', '#ffb562', 'DC',
    "Sega's last console. Runs in RetroArch; needs its BIOS."],
  naomi: ['naomi.png', 'Naomi', 'Sega', '1998', '#6fd6d6', 'NAOMI',
    'The arcade board related to the Dreamcast. Runs in RetroArch; needs its BIOS.'],
  naomigd: ['naomi.png', 'Naomi GD-ROM', 'Sega', '2001', '#6fd0b8', 'GD',
    'Naomi arcade games shipped on GD-ROM. Runs in RetroArch; needs its BIOS.'],
  atomiswave: ['atomiswave.png', 'Atomiswave', 'Sammy', '2003', '#ff9a6a', 'AW',
    "Sammy's cartridge arcade board. Runs in RetroArch; needs its BIOS."],
  pcengine: ['pcengine.png', 'PC Engine', 'NEC', '1987 / 1989', '#e8e8f0', 'PCE',
    "NEC's small console built for shooters, on HuCard. Runs in RetroArch."],
  pcenginecd: ['pcenginecd.png', 'PC Engine CD', 'NEC', '1988 / 1989', '#ff9191', 'PCE CD',
    'The PC Engine with a CD-ROM drive. Runs in RetroArch; needs its BIOS.'],
  supergrafx: ['supergrafx.png', 'SuperGrafx', 'NEC', '1989', '#d6b494', 'SGX',
    'An upgraded PC Engine with a handful of games. Runs in RetroArch.'],
  mame: ['arcade.png', 'Arcade', 'MAME', '', '#ffd36a', 'ARC',
    "Arcade machines, one ROM set per board. Runs in RetroArch's MAME core."],
}

/** The four application packs, dressed. Ids match catalog/<id>/pack.json. */
export const appStyles = {
  steam: {color: '#71b8e8', tile: '#1c2232', scale: 1.02, category: 'PC games',
    edition: 'Big Picture',
    description: 'Steam in Big Picture mode, made for a controller.'},
  youtube: {color: '#ff777f', tile: '#ff0000', scale: 1.43, category: 'Videos',
    edition: 'YouTube TV',
    description: 'YouTube’s TV interface.'},
  twitch: {color: '#bd9aff', tile: '#a544ff', scale: 1.66, category: 'Live',
    edition: 'EmberTV',
    description: 'Twitch through EmberTV, the TV interface from the GameCore pack.'},
  stremio: {color: '#b6a0ff', tile: '#7b5bf5', scale: 1.04, category: 'Movies & series',
    edition: 'TV interface',
    description: 'Stremio with its TV interface.'},
}

const DEFAULT_APP = {color: '#8dc0f5', tile: '#203757', scale: 1,
  category: 'Application', edition: 'GameCore pack',
  description: 'An application from your GameCore catalogue.'}

export const isApp = (s) => s?.kind === 'app' || s?.type === 'app' || s?.type === 'application'
/** Legacy tuple accessor retained for compatibility. */
export const meta = (s) => consoles[s?.id] || null
/** Named view over the legacy tuple, so existing runtime mutations remain observable. */
const profile = (s) => {
  const row = meta(s)
  if (!row) return null
  return {file: row[0], name: row[1], maker: row[2], year: row[3],
    accent: row[4], mark: row[5], story: row[6]}
}
export const systemName = (s) => isApp(s)
  ? (s?.label || s?.id || 'Application')
  : s?.platform || profile(s)?.name || s?.label || s?.id || 'Collection'
export const systemMark = (s) => profile(s)?.mark || (s?.label || s?.id || '?').slice(0, 6)
export const systemMaker = (s) => profile(s)?.maker || ''
export const systemYear = (s) => profile(s)?.year || ''
export const systemStory = (s) => profile(s)?.story
  || 'Part of your collection. Open it to browse the games you have added.'
export const appStyle = (s) => appStyles[s?.id] || DEFAULT_APP
export const accent = (sdk, s) =>
  isApp(s) ? appStyle(s).color : (profile(s)?.accent || (s && sdk.format.systemColor(s)) || '#8dc0f5')

export const packLogo = (s) => s?.iconPath
  ? `/assets/logos/${encodeURIComponent(s.iconPath.replace(/\\/g, '/').split('/').pop())}`
  : null
export const coverUrl = (systemId, filename) =>
  `/api/covers/${encodeURIComponent(systemId)}/${encodeURIComponent(filename)}`
export const consoleFile = (s) => profile(s)?.file || null
export const consoleArt = (sdk, s) => {
  const file = consoleFile(s)
  return file ? sdk.system.asset(`assets/consoles/${file}`) : packLogo(s)
}

/** Favourites, in the browser and nowhere else.
 *
 * GameCore has no favourites of its own — no endpoint, no column — so this is
 * the theme's, and it says so. `localStorage` is per-box and survives a reload,
 * which is the whole promise being made. Keyed by `system:filename`, the same
 * pair the playtime table uses, because a filename alone collides across two
 * consoles holding the same game.
 */
const KEY = 'orbit-favourites'
const listeners = new Set()
let favourites = new Set()
try {
  const saved = JSON.parse(localStorage.getItem(KEY) || '[]')
  if (Array.isArray(saved)) favourites = new Set(saved.filter((v) => typeof v === 'string'))
} catch { /* a box with storage disabled simply has no favourites */ }

export const favouriteKey = (systemId, filename) => `${systemId}:${filename}`
export const isFavourite = (systemId, filename) =>
  favourites.has(favouriteKey(systemId, filename))
export const favouriteCount = () => favourites.size
export function toggleFavourite(systemId, filename) {
  const key = favouriteKey(systemId, filename)
  if (favourites.has(key)) favourites.delete(key)
  else favourites.add(key)
  try { localStorage.setItem(KEY, JSON.stringify([...favourites])) } catch { /* ignore */ }
  listeners.forEach((fn) => fn())
  return favourites.has(key)
}
export function onFavouritesChange(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** `Zelda_(USA).iso` → `Zelda`.
 *
 * A playtime row and a suspended session are both keyed by the ROM FILENAME,
 * which is not a title. Everywhere the library is involved the backend has
 * already run `clean_name` and handed the UI a `display_name`; from a key alone
 * the same two steps have to happen here — drop the extension, drop the
 * bracketed and parenthesised tags — before `sdk.format.gameName`. Without it
 * the rail is the one place in the interface that calls a game by its file.
 * Kept in step with backend/services/rom_scanner.py on purpose.
 */
export const titleFromKey = (sdk, key) => sdk.format.gameName(
  String(key || '').replace(/\.[^.]+$/, '').replace(/[([{][^)\]}]*[)\]}]/g, '').trim())
