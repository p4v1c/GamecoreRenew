/** Favourites, in this browser only: GameCore has none of its own. Keyed
 * `system:filename`, as playtime is, so two consoles never share a favourite.
 * One list per profile (`followProfiles`); the primary keeps the list it had. */
const BASE = 'jelly-favourites'
const listeners = new Set()
let key = BASE
let saved = read()

function read() {
  try {
    const raw = JSON.parse(localStorage.getItem(key) || '[]')
    if (Array.isArray(raw)) return new Set(raw.filter((v) => typeof v === 'string'))
  } catch { /* storage disabled: no favourites, nothing else changes */ }
  return new Set()
}

/** Switch to the active profile's list now and on every change. */
export function followProfiles(sdk) {
  const players = sdk.players
  if (!players?.storageKey) return () => {}
  const reload = () => {
    key = players.storageKey(BASE)
    saved = read()
    listeners.forEach((fn) => fn())
  }
  reload()
  return players.onChange(reload)
}

const keyOf = (systemId, filename) => `${systemId}:${filename}`

export const isFavourite = (systemId, filename) => saved.has(keyOf(systemId, filename))
export const favouriteCount = () => saved.size
/** Every favourite as `system:filename`, the standby playlist's weighting. */
export const favouriteKeys = () => [...saved]

export function toggleFavourite(systemId, filename) {
  const k = keyOf(systemId, filename)
  if (saved.has(k)) saved.delete(k)
  else saved.add(k)
  try { localStorage.setItem(key, JSON.stringify([...saved])) } catch { /* ignore */ }
  listeners.forEach((fn) => fn())
  return saved.has(k)
}

export function onFavouritesChange(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** Re-render on any favourite change. */
export const createUseFavourites = (sdk) => function useFavourites() {
  const {useState, useEffect} = sdk.ui
  const [, bump] = useState(0)
  useEffect(() => onFavouritesChange(() => bump((n) => n + 1)), [])
}
