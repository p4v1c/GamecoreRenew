import {isApp, titleFromKey} from './catalog.js'

/** Every game on the box, across consoles, with its playtime.
 *
 * Play, Collection and search all draw from the same list, so it is loaded
 * once and shared. The host's `__all__` library does the same walk, but only
 * for the library screen; this one lives on the dashboard.
 *
 * A console whose list fails is skipped, not fatal: the rest of the collection
 * still shows. Only when every console fails is the whole thing an error, and
 * then the views offer a retry.
 */
export function createCollection(sdk) {
  const {useState, useEffect} = sdk.ui
  let state = {status: 'idle', games: [], failed: 0}
  let systems = []
  let token = 0
  const listeners = new Set()
  const publish = (next) => { state = next; listeners.forEach((fn) => fn(state)) }

  async function load(next = systems) {
    systems = next || []
    const mine = ++token
    const machines = systems.filter((s) => !isApp(s))
    publish({...state, status: state.games.length ? 'refreshing' : 'loading'})
    let failed = 0
    const [played, lists] = await Promise.all([
      sdk.api.playtime.all().catch(() => []),
      Promise.all(machines.map((system) => sdk.api.games.list(system.id)
        .then((games) => (Array.isArray(games) ? games : []).map((g) => ({g, system})))
        .catch(() => { failed++; return [] }))),
    ])
    if (mine !== token) return
    const history = new Map((Array.isArray(played) ? played : [])
      .map((p) => [`${p.system_id}:${p.game_key}`, p]))
    const games = lists.flat().filter(({g}) => g?.filename).map(({g, system}) => {
      const key = `${system.id}:${g.filename}`
      const p = history.get(key)
      return {
        kind: 'game', key, systemId: system.id, system, gameKey: g.filename, path: g.path,
        title: g.display_name || titleFromKey(sdk, g.filename), ext: g.ext,
        seconds: p?.total_secs || 0, lastPlayed: p?.last_played || null,
      }
    }).sort((a, b) => a.title.localeCompare(b.title, 'fr', {sensitivity: 'base'}))
    const allFailed = machines.length > 0 && failed === machines.length
    publish({status: allFailed ? 'error' : 'ready', games, failed})
  }

  // Playtime moves after every session, and an emulator install adds a console.
  const refresh = () => { if (systems.length) load(systems) }
  sdk.system.onWsEvent('game:finished', refresh)
  sdk.system.onWsEvent('catalog:done', refresh)
  sdk.system.onWsEvent('playtime:rekeyed', refresh)

  /** The shared list; `systems` is what the host already fetched for Home. */
  function useCollection(next) {
    const [snap, setSnap] = useState(state)
    useEffect(() => {
      listeners.add(setSnap)
      setSnap(state)
      return () => listeners.delete(setSnap)
    }, [])
    useEffect(() => {
      if (next && next !== systems) load(next)
    }, [next])
    return snap
  }

  return {useCollection, retry: refresh, get: () => state}
}

/** Most recently played first, then the rest by title. */
export const byRecent = (games) => [...games].sort((a, b) =>
  String(b.lastPlayed || '').localeCompare(String(a.lastPlayed || '')))

/** Lower-case, accents gone, so "pokemon" finds "Pokémon". */
export const fold = (s) => String(s || '').normalize('NFD')
  .replace(/[̀-ͯ]/g, '').toLowerCase()
