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
    'The beginning of a new dimension. Rediscover the adventures that brought gaming into the 3D era.'],
  pcsx2: ['ps2.png', 'PlayStation 2', 'Sony', '2000', '#749dff', 'PS2',
    'An iconic silhouette. An unforgettable generation. Return to the classics that defined an era.'],
  rpcs3: ['ps3.png', 'PlayStation 3', 'Sony', '2006', '#b59afa', 'PS3',
    'Bigger worlds. Deeper stories. Rediscover a generation of adventures in high definition.'],
  shadps4: ['ps4.png', 'PlayStation 4', 'Sony', '2013', '#5cafff', 'PS4',
    'Great stories and new horizons. Your PlayStation collection keeps growing.'],
  ppsspp: ['psp.png', 'PlayStation Portable', 'Sony', '2004', '#9cacf2', 'PSP',
    'Great adventures in the palm of your hand. Rediscover the first PlayStation handheld.'],
  cemu: ['wiiu.png', 'Nintendo Wii U', 'Nintendo', '2012', '#6cdae9', 'Wii U',
    'Two screens. New ways to play. Step into worlds full of color.'],
  dolphin: ['gamecube.png', 'GameCube & Wii', 'Nintendo', '2001 / 2006', '#ae91f5', 'GC',
    'A little cube with big ideas, and gaming in motion. Two Nintendo generations in your collection.'],
  ryujinx: ['switch.png', 'Nintendo Switch', 'Nintendo', '2017', '#ff8292', 'Switch',
    'Play without boundaries. Rediscover your hybrid collection, from the living room to grand adventures.'],
  azahar: ['3ds.png', 'Nintendo 3DS', 'Nintendo', '2011', '#93cde9', '3DS',
    'Open a new dimension. Two screens for adventures big and small.'],
  melonds: ['ds.png', 'Nintendo DS', 'Nintendo', '2004', '#b9c7ef', 'DS',
    'Two screens. A thousand ideas. Touchscreen classics come to life in your collection.'],
  mgba: ['gba.png', 'Game Boy Advance', 'Nintendo', '2001', '#aa97e8', 'GBA',
    'A world of pixels. Your favorite pocket adventures, now on the big screen.'],
  gopher64: ['n64.png', 'Nintendo 64', 'Nintendo', '1996', '#7cd0a0', 'N64',
    'The great leap into 3D. Rediscover the worlds that changed the way we play.'],
  rmg: ['n64.png', 'Nintendo 64', 'Nintendo', '1996', '#7cd0a0', 'N64',
    'The great leap into 3D. Rediscover the worlds that changed the way we play.'],
  xenia: ['xbox360.png', 'Xbox 360', 'Microsoft', '2005', '#a5d998', '360',
    'A new generation of memories. Your Xbox classics, all in one place.'],
}

/** The four application packs, dressed. Ids match catalog/<id>/pack.json. */
export const appStyles = {
  steam: {color: '#71b8e8', tile: '#1c2232', scale: 1.02, category: 'PC GAMES',
    edition: 'Big Picture',
    description: 'Your PC library belongs in the living room. Explore Steam in an interface built for your controller.'},
  youtube: {color: '#ff777f', tile: '#ff0000', scale: 1.43, category: 'VIDEOS',
    edition: 'YouTube TV',
    description: 'New discoveries, your favorite creators, and videos you love. Settle in and find something to watch.'},
  twitch: {color: '#bd9aff', tile: '#a544ff', scale: 1.66, category: 'LIVE',
    edition: 'EmberTV',
    description: 'Your streams and communities on the big screen. Watch live with the TV interface in the GameCore pack.'},
  stremio: {color: '#b6a0ff', tile: '#7b5bf5', scale: 1.04, category: 'MOVIES & SERIES',
    edition: 'TV interface',
    description: 'Your home cinema, just a button away. Enjoy Stremio in an interface made for the living room.'},
}

const DEFAULT_APP = {color: '#8dc0f5', tile: '#203757', scale: 1,
  category: 'APPLICATION', edition: 'GameCore pack',
  description: 'An application from your GameCore catalogue.'}

export const isApp = (s) => s?.kind === 'app' || s?.type === 'app' || s?.type === 'application'
export const meta = (s) => consoles[s?.id] || null
export const systemName = (s) =>
  s?.platform || meta(s)?.[1] || s?.label || s?.id || 'Collection'
export const systemMark = (s) => meta(s)?.[5] || (s?.label || s?.id || '?').slice(0, 6)
export const systemMaker = (s) => meta(s)?.[2] || ''
export const systemYear = (s) => meta(s)?.[3] || ''
export const systemStory = (s) => meta(s)?.[6]
  || 'Part of your collection. Open it to browse the games you have added.'
export const appStyle = (s) => appStyles[s?.id] || DEFAULT_APP
export const accent = (sdk, s) =>
  isApp(s) ? appStyle(s).color : (meta(s)?.[4] || (s && sdk.format.systemColor(s)) || '#8dc0f5')

export const packLogo = (s) => s?.iconPath
  ? `/assets/logos/${encodeURIComponent(s.iconPath.replace(/\\/g, '/').split('/').pop())}`
  : null
export const coverUrl = (systemId, filename) =>
  `/api/covers/${encodeURIComponent(systemId)}/${encodeURIComponent(filename)}`
export const consoleArt = (sdk, s) => {
  const file = meta(s)?.[0]
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
