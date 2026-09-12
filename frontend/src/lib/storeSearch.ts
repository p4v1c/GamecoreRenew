/**
 * Searching for a game, and the single implementation of it.
 *
 * The Store's Games tab is two steps: pick a console, then search inside it.
 * This is everything that step means except where the cursor is — the chosen
 * console, the query, the request, what came back and what did not, and the
 * result the player has asked about. `StoreScreen` consumes it; nothing else
 * does yet, and the point of it being a module is that the second consumer
 * cannot start a second copy.
 *
 * That is not a hypothetical here. `catalog.ts` beside this file exists
 * because the same sequence had been written out three times and the copies
 * had already drifted on three points — one of them a destructive removal that
 * asked once in one copy and twice in the other. The rule that came out of it
 * is that a *decision* lives in one place; the cursor, which is navigation,
 * stays with the screen that owns it.
 *
 * ── Why the console is chosen first ─────────────────────────────────────────
 * Not a preference about menus. The ingestion class of a download is a
 * property of the **pair** (system, incoming format) — the same `.zip` is the
 * ROM on `mame` and packaging on `snes9x` — and the directory it has to land
 * in is `<DATA>/emu/<roms.dir>/`, which is a property of the system. A result
 * found without a console attached could be neither placed nor classified, and
 * no indexer labels its own results by console reliably enough to attach one
 * afterwards. See `docs/architecture/14-store-ingestion-matrix.md` §0 and §1.3.
 *
 * ── Why only installed consoles ─────────────────────────────────────────────
 * A game for a console that is not on the box lands in a directory nothing
 * scans, for a tile that is not on the grid. The list comes from
 * `useCatalog({ kind: 'emulator' })`, which the Consoles tab already holds —
 * this module does not read the catalogue a second time, because two readers
 * of one fact is how two screens come to disagree about it.
 *
 * ── What is deliberately not here ───────────────────────────────────────────
 * Downloading. Nothing in this file fetches a game, writes a file or queues
 * anything, and `ask()` records a choice in component state that dies with the
 * screen. Acquisition and the job that survives a reboot are separate steps
 * with their own seams; half of one built here would have to be undone.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type CatalogEntry, type StoreSearchResult } from '../api'
import { playSound } from './sounds'

/** What a failed search leaves on screen. Distinct from "nothing matched". */
export const SEARCH_FAILED = 'That search did not come back.'

/**
 * Bytes as a television can read them at two metres.
 *
 * One decimal and binary units, which is what every other size on this box
 * means. It lives here rather than in `lib/format.ts` because that file is
 * `sdk.format` — the theme-facing contract — and growing it is an SDK version
 * bump this step has no reason to spend.
 */
export function formatSize(bytes: number): string {
  if (!bytes || bytes < 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let n = bytes
  let i = 0
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++ }
  return `${n < 10 && i > 0 ? n.toFixed(1) : Math.round(n)} ${units[i]}`
}

export interface StoreSearchState {
  /** The console being searched. `null` until the player picks one. */
  system: CatalogEntry | null
  /** What was last searched for; `''` before the first search. */
  query: string
  results: StoreSearchResult[]
  /**
   * Where a download for this console would land — `emu/<dir>`, relative to
   * the data root. Answered by the endpoint rather than built here: it is the
   * pack's `roms.dir` and a frontend guessing it from the id would be right
   * for thirty packs and wrong for the one that is renamed.
   */
  romsDir: string
  /**
   * Whether the rows describe real sources.
   *
   * `false` for the demo provider, which invents them. Surfaced rather than
   * swallowed: a tab that drew invented rows exactly like an indexer's would
   * invite a player to press ✕ on a game that does not exist.
   */
  live: boolean
  providerLabel: string
  /** A search is in flight. */
  loading: boolean
  /** The search failed. `''` when nothing is wrong — an empty result set is
   *  not an error and must not be drawn as one. */
  error: string
  /** True once a search has answered, so "nothing matched" can be told apart
   *  from "nothing has been searched for yet". */
  answered: boolean
  /** The result the player has asked about, `null` when none. */
  asked: StoreSearchResult | null

  /** Pick the console to search inside. Clears whatever the last one found. */
  choose: (system: CatalogEntry) => void
  /** Run a search in the chosen console. A no-op with no console. */
  run: (query: string) => Promise<void>
  /** Ask about one result. Records the choice; downloads nothing. */
  ask: (result: StoreSearchResult) => void
  /** Put an asked result back down. */
  unask: () => void
  /** Step back out of the console, to the list of them. */
  leave: () => void
}

export function useStoreSearch(): StoreSearchState {
  const [system, setSystem] = useState<CatalogEntry | null>(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<StoreSearchResult[]>([])
  const [romsDir, setRomsDir] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [answered, setAnswered] = useState(false)
  const [asked, setAsked] = useState<StoreSearchResult | null>(null)
  const [live, setLive] = useState(false)
  const [providerLabel, setProviderLabel] = useState('')

  /**
   * Which request is still wanted.
   *
   * Bumped by every search and by every change of console, so a slow answer
   * for "mario" cannot land on top of a fast one for "zelda". The library
   * carries the same guard for the same reason: the requests are not
   * cancellable and they do not come back in the order they were sent.
   */
  const wanted = useRef(0)

  // Asked once, on mount. Which provider is answering does not change while a
  // screen is open — and the Store is mounted only while it is open, so this
  // is one request per visit rather than one per boot.
  useEffect(() => {
    let alive = true
    api.store.provider()
      // Coerced rather than trusted: this lands in the view props typed as a
      // string, and an endpoint answering a shape nobody expected must not put
      // `undefined` where a theme is about to render one.
      .then(p => {
        if (!alive) return
        setLive(!!p?.live)
        setProviderLabel(String(p?.label || p?.name || ''))
      })
      // Left as "not live", which is the cautious answer: a tab that assumed
      // real sources because one request failed would be the dishonest half of
      // this whole tab.
      .catch(() => {})
    return () => { alive = false }
  }, [])

  const systemRef = useRef(system)
  systemRef.current = system

  const run = useCallback(async (q: string) => {
    const target = systemRef.current
    const cleaned = q.trim()
    // No console is not an error to report — it is a step the player has not
    // taken, and the screen is showing them the list of consoles while it is
    // true.
    if (!target || !cleaned) return

    const mine = ++wanted.current
    setQuery(cleaned)
    setLoading(true)
    setError('')
    playSound('confirm')
    try {
      const answer = await api.store.search(target.id, cleaned)
      if (wanted.current !== mine) return
      setResults(answer.results ?? [])
      setRomsDir(answer.romsDir ?? '')
      setLive(!!answer.live)
      setAnswered(true)
    } catch {
      if (wanted.current !== mine) return
      // The rows that were there are dropped, and that is the honest answer
      // here where `useCatalog` keeps its list: these belong to a request that
      // failed, not to a list the box maintains. Keeping them would leave the
      // last query's results under the new query's title.
      setResults([])
      setAnswered(false)
      setError(SEARCH_FAILED)
    } finally {
      if (wanted.current === mine) setLoading(false)
    }
  }, [])

  const choose = useCallback((next: CatalogEntry) => {
    wanted.current++          // whatever was in flight is for another console
    setSystem(next)
    setQuery('')
    setResults([])
    setRomsDir('')
    setAnswered(false)
    setError('')
    setAsked(null)
    setLoading(false)
  }, [])

  const leave = useCallback(() => {
    wanted.current++
    setSystem(null)
    setQuery('')
    setResults([])
    setRomsDir('')
    setAnswered(false)
    setError('')
    setAsked(null)
    setLoading(false)
  }, [])

  const ask = useCallback((result: StoreSearchResult) => {
    // Records it and nothing else. There is no request to send: acquiring the
    // bytes is a later step, and a call that answered "accepted" while nothing
    // downloaded would be the button that does nothing.
    setAsked(result)
    playSound('confirm')
  }, [])

  const unask = useCallback(() => setAsked(null), [])

  return {
    system, query, results, romsDir, live, providerLabel,
    loading, error, answered, asked,
    choose, run, ask, unask, leave,
  }
}
