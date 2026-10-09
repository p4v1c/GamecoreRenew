/**
 * What the Studio home knows about the console in front of you, beyond what
 * the host hands the dashboard.
 *
 * The host gives `homeView` one number per system: the game count and the
 * summed playtime. The copy block also wants the games that were played last,
 * how long each one was played, and the ROM path of the most recent so △ can
 * pick it back up. Two requests answer that, both already used elsewhere:
 *
 *   sdk.api.playtime.all()       every (system, game) row, for the active profile
 *   sdk.api.games.list(system)   the shelf, for display names and ROM paths
 *
 * The playtime rows are fetched once and again whenever the dashboard comes
 * back into view, since that is the only moment they can have changed (a game
 * was just played), plus on `playtime:rekeyed` and on a profile switch. The
 * shelves are fetched lazily, for the focused console only, after the cursor
 * has rested for a moment — walking past thirty consoles must not queue thirty
 * library scans — and cached until the dashboard is shown again.
 */

/** How long the cursor rests on a console before its shelf is asked for. */
const SETTLE_MS = 160
/** Covers in the "Recently played" strip. */
const RECENT_MAX = 4

export const createHomeData = (sdk) => {
  const { useState, useEffect, useRef } = sdk.ui
  const shelves = new Map()          // systemId -> games[] (or a pending promise)

  const shelf = (id) => {
    if (!shelves.has(id)) {
      shelves.set(id, sdk.api.games.list(id)
        .then((g) => (Array.isArray(g) ? g : []))
        .catch(() => { shelves.delete(id); return [] }))
    }
    return shelves.get(id)
  }

  /** Every playtime row, refreshed whenever it can have changed. */
  const usePlaytimeRows = () => {
    const [rows, setRows] = useState([])
    const [epoch, setEpoch] = useState(0)
    const screen = sdk.nav.use((s) => s.screen)

    useEffect(() => sdk.system.onWsEvent('playtime:rekeyed', () => setEpoch((n) => n + 1)), [])
    useEffect(() => sdk.players?.onChange?.(() => setEpoch((n) => n + 1)), [])
    useEffect(() => {
      if (screen !== 'home') return
      let live = true
      // A game just played may have added a ROM path or a playtime row.
      shelves.clear()
      sdk.api.playtime.all()
        .then((r) => { if (live) setRows(Array.isArray(r) ? r : []) })
        .catch(() => {})
      return () => { live = false }
    }, [screen, epoch])
    return rows
  }

  /**
   * The focused console's recently played games, newest first, each with its
   * display name, ROM path and seconds played. Empty for an app, for a console
   * nobody has played, and while the shelf is still on its way.
   */
  const useRecent = (system, rows, isApp) => {
    const [recent, setRecent] = useState({ id: null, games: [] })
    const timer = useRef(null)

    useEffect(() => {
      clearTimeout(timer.current)
      const id = system?.id
      if (!id || isApp) { setRecent({ id, games: [] }); return }
      const mine = rows
        .filter((r) => r.system_id === id && r.last_played)
        .sort((a, b) => String(b.last_played).localeCompare(String(a.last_played)))
      if (!mine.length) { setRecent({ id, games: [] }); return }

      let live = true
      timer.current = setTimeout(() => {
        shelf(id).then((games) => {
          if (!live) return
          const byFile = new Map(games.map((g) => [g.filename, g]))
          // A row for a ROM that has since left the shelf is history, not
          // something to show a cover for or to launch.
          const out = mine.map((r) => {
            const g = byFile.get(r.game_key)
            return g ? { ...g, secs: r.total_secs || 0, last: r.last_played } : null
          }).filter(Boolean).slice(0, RECENT_MAX)
          setRecent({ id, games: out })
        })
      }, SETTLE_MS)
      return () => { live = false; clearTimeout(timer.current) }
    }, [system?.id, rows, isApp])

    // Never show one console's covers under another's name.
    return recent.id === system?.id ? recent.games : []
  }

  return { usePlaytimeRows, useRecent }
}

/** "25 min", "2 h 40", "3 h" — the long form, for a screen read from a sofa. */
export const duration = (secs) => {
  if (!secs || secs < 60) return secs ? '< 1 min' : null
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (!h) return `${m} min`
  return m ? `${h} h ${String(m).padStart(2, '0')}` : `${h} h`
}

/** "Today", "Yesterday", "Sep 30", or "Sep 30, 2025" outside this year. */
export const when = (iso) => {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const now = new Date()
  const start = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const days = Math.round((start(now) - start(d)) / 86400000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  const opts = { month: 'short', day: 'numeric' }
  if (d.getFullYear() !== now.getFullYear()) opts.year = 'numeric'
  return d.toLocaleDateString('en-US', opts)
}
