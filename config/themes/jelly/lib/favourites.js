/** Favourites, in this browser only: GameCore has none of its own. Keyed
 * `system:filename`, as playtime is, so two consoles never share a favourite. */
const KEY = 'jelly-favourites'
const listeners = new Set()
let saved = new Set()
try {
  const raw = JSON.parse(localStorage.getItem(KEY) || '[]')
  if (Array.isArray(raw)) saved = new Set(raw.filter((v) => typeof v === 'string'))
} catch { /* storage disabled: no favourites, nothing else changes */ }

const keyOf = (systemId, filename) => `${systemId}:${filename}`

export const isFavourite = (systemId, filename) => saved.has(keyOf(systemId, filename))
export const favouriteCount = () => saved.size

export function toggleFavourite(systemId, filename) {
  const k = keyOf(systemId, filename)
  if (saved.has(k)) saved.delete(k)
  else saved.add(k)
  try { localStorage.setItem(KEY, JSON.stringify([...saved])) } catch { /* ignore */ }
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
