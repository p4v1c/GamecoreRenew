/**
 * StoreScreen — the Store's behaviour.
 *
 * Where the player goes to put a console on the box and, later, to bring a game
 * onto it. A destination, not a settings page: `screen === 'store'` sits beside
 * `'home'` and `'library'` in the store, and the shell shows it the same way it
 * shows those two. Settings is where you change what the box already does; this
 * is where you change what it HAS.
 *
 * The markup lives in a view component, default or themed. This file is what
 * guarantees they behave identically: the tabs, the focus, the paging and the
 * gamepad bindings are here, and a theme cannot replace them.
 *
 * ── What this screen reads, and what it does with it ────────────────────────
 * `GET /api/catalog`, filtered to `kind: 'emulator'`. Installing, removing and
 * reconfiguring a console are done from here — this is the only screen that
 * does them, the settings keep the four applications and nothing else. None of
 * that sequence is written in this file: it is `useCatalog` in `lib/catalog.ts`,
 * the one implementation, which the applications page consumes too. What IS
 * this file's is the cursor, and therefore the two things the cursor touches —
 * the order of the list, and which button acts on the row under it.
 *
 * The Games tab is the same shape with two more modules behind it:
 * `useStoreSearch` in `lib/storeSearch.ts` owns the chosen console, the query
 * and what came back; `useStoreJobs` in `lib/storeJobs.ts` owns the queue of
 * what the player has asked for. This file owns the cursor walking all three
 * lists. The search order is not a menu preference: the ingestion class of a
 * download is a property of the pair (system, incoming format) and the target
 * directory is a property of the system, so a result found without a console
 * attached could be neither placed nor classified
 * (`docs/architecture/14-store-ingestion-matrix.md` §0, §1.3).
 *
 * **Asking for a game now queues it, and queueing it does not download it.**
 * The row is real and it is in the box's database, so it survives this screen
 * and a reboot; what is not real yet is anything behind the worker that runs
 * it, so every job ends `failed` saying so. `gamesDownloadReady` stays false
 * and is what a view must read before it promises bytes.
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useStore } from '../../store'
import { type CatalogEntry, type StoreJob, type StoreSearchResult } from '../../api'
import { onGp } from '../../hooks/useGamepad'
import { useCatalog } from '../../lib/catalog'
import { useStoreJobs } from '../../lib/storeJobs'
import { useStoreSearch } from '../../lib/storeSearch'
import { Overlay } from '../ui'
import { VirtualKeyboard } from '../ui/VirtualKeyboard'
import DefaultStoreView from './DefaultStoreView'
import {
  STORE_TABS, STORE_TAB_LABELS,
  type StoreGamesPhase, type StoreTab, type StoreViewProps,
} from './types'

/**
 * The grid, in cards per page.
 *
 * Three rows rather than the dashboard's two: this list is the whole catalogue
 * — thirty-one consoles — and not the handful the player has installed, so a
 * 4 × 2 page would be four pages of scenery to walk through.
 */
const COLS = 4
const ROWS = 3
const PER_PAGE = COLS * ROWS

/**
 * A page of search results, which is a column and not a grid.
 *
 * A result is a filename, a size and a format — a line of text, not a card —
 * and four of them side by side on a television is four truncated names. So
 * the results phase pages one per row, and the shape travels to the view in
 * `cols`/`rows`/`perPage` rather than being a second thing a theme has to know.
 */
const RESULT_ROWS = 7

interface Props {
  view?: React.ComponentType<StoreViewProps>
  /** Shortcuts the theme binds itself; see ShellParts.storeOmit. */
  omit?: string[]
}

export default function StoreScreen({ view: View = DefaultStoreView, omit }: Props = {}) {
  // One subscription per value, for the reason shellRerender.test.tsx states:
  // a bare `useStore()` subscribes to every field, and this screen would then
  // re-render on a cursor step taken on another screen entirely.
  const screen = useStore(s => s.screen)
  const modalDepth = useStore(s => s.modalDepth)
  const goHome = useStore(s => s.goHome)

  const [tab, setTab] = useState<StoreTab>('consoles')
  const [focusIdx, setFocusIdx] = useState(0)
  const [page, setPage] = useState(0)
  const [showSearch, setShowSearch] = useState(false)
  /**
   * Whether the queue is the thing on screen.
   *
   * Its own flag rather than derived from the search state like the other two
   * phases, because it is not a step of the search: the queue is reachable
   * with nothing searched for and with no console chosen, and closing it has
   * to put the player back wherever they were rather than somewhere the
   * search state happens to imply.
   */
  const [queueOpen, setQueueOpen] = useState(false)

  const screenRef = useRef(screen)
  const modalDepthRef = useRef(modalDepth)
  useEffect(() => { screenRef.current = screen }, [screen])
  useEffect(() => { modalDepthRef.current = modalDepth }, [modalDepth])

  /**
   * Everything the bindings and the handlers below read at the moment they run,
   * rather than at the moment they were registered.
   *
   * Same fix as HomeScreen and LibraryScreen, written for the same reason: the
   * d-pad is edge-triggered, so a burst of presses arrives before React has
   * re-rendered, and every handler closing over the render that registered it
   * computes the same destination from the same stale cursor. Assigned during
   * render further down, so they are current from the first press after a
   * change; declared up here because `onDone` below reads them.
   *
   * The cursor is component state here and not the store's — `gridFocusIdx`
   * belongs to the dashboard, and borrowing it would move the player's tile
   * while they shopped. So these refs are the live read, where HomeScreen can
   * use `useStore.getState()`.
   */
  const consolesRef = useRef<CatalogEntry[]>([])
  const focusRef = useRef(focusIdx)
  const pageRef = useRef(page)
  const countRef = useRef(0)
  const pageCountRef = useRef(0)
  const tabRef = useRef(tab)
  /** Whatever the cursor is walking: packs on the Consoles tab, and on the
   *  Games tab a console, a result or a queued job depending on the phase. */
  const itemsRef = useRef<(CatalogEntry | StoreSearchResult | StoreJob)[]>([])
  /** The page shape, which is the results list's and not the grid's while the
   *  Games tab is showing results. Read live for the same reason as the rest:
   *  a burst of presses arrives before the render that changed them. */
  const colsRef = useRef(COLS)
  const rowsRef = useRef(ROWS)
  const perPageRef = useRef(PER_PAGE)
  const phaseRef = useRef<StoreGamesPhase>('systems')
  const showSearchRef = useRef(showSearch)

  /**
   * The list after a pack is installed or removed — here or anywhere else.
   *
   * The focus is kept by pack id rather than by index: the grid that comes back
   * is a different grid, and holding position 7 when position 7 is now a
   * different console moves the player's cursor for them. The pack that has
   * just been removed is the one case with no answer, and the clamp below
   * catches it.
   *
   * Recorded for a failed run too. A run that failed can still have changed the
   * list — see `useCatalog`, which re-reads either way — and a cursor is no
   * less worth keeping still when the news is bad.
   */
  const keepFocusOn = useRef<string | null>(null)

  const catalog = useCatalog({
    kind: 'emulator',
    onDone: () => {
      // Only the Consoles tab's cursor walks this list. On the Games tab the
      // page and focus belong to another one entirely, and reading a pack out
      // of them would pin the cursor to whatever that arithmetic happened to
      // land on.
      keepFocusOn.current = tabRef.current === 'consoles'
        ? consolesRef.current[pageRef.current * PER_PAGE + focusRef.current]?.id ?? null
        : null
    },
  })

  const catalogRef = useRef(catalog)
  catalogRef.current = catalog

  /**
   * The Games tab's own state — the console, the query, the rows.
   *
   * A second module beside `useCatalog`, and not a second copy of it: what
   * they share is that neither of them may be reimplemented in a view. See
   * `lib/storeSearch.ts` for what it owns and why the console comes first.
   */
  const search = useStoreSearch()
  const searchRef = useRef(search)
  searchRef.current = search

  /**
   * The queue — what has already been asked for, and what became of it.
   *
   * A third module and not a third copy, on the same rule as the two above: a
   * view may draw the rows and may not decide what a state means, which row
   * can still be stopped, or what happens when one is. Mounted with the
   * screen, so a player who never opens the Store never asks for the list.
   */
  const jobs = useStoreJobs()
  const jobsRef = useRef(jobs)
  jobsRef.current = jobs

  /**
   * The on-screen keyboard counts as a modal while it is up.
   *
   * Same as the library's: the shell binds Options → Settings and Share →
   * Power globally, and without this they open a second surface on top of a
   * player who is typing.
   */
  const openModal = useStore(s => s.openModal)
  const closeModal = useStore(s => s.closeModal)
  useEffect(() => {
    if (!showSearch) return
    openModal()
    return () => closeModal()
  }, [showSearch]) // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * Consoles are the emulator packs, A–Z by label.
   *
   * The order is the label rather than the id the endpoint sorts by, because
   * the cursor walks this list and "Nintendo 64" is what is printed on the card
   * — an A–Z the player can see is the only ordering a d-pad can be steered
   * through. It is decided here and not in `useCatalog` and not in the view for
   * exactly that reason: the order IS the navigation, so it belongs with the
   * cursor and cannot be a theme's to change.
   */
  const consoles = useMemo(
    () => [...(catalog.rows ?? [])].sort((a, b) => a.label.localeCompare(b.label)),
    [catalog.rows],
  )

  /**
   * The consoles a game can be searched for: the installed ones.
   *
   * Filtered from the list the Consoles tab already holds rather than read
   * again — two readers of one fact is how two screens come to disagree about
   * it, which is the whole lesson `useCatalog` was written from. A game for a
   * console that is not on the box would land in a directory nothing scans,
   * for a tile that is not on the grid.
   */
  const gamesSystems = useMemo(
    () => consoles.filter(c => c.installed),
    [consoles],
  )

  /**
   * Which step of the Games tab the player is on.
   *
   * One expression, so there is no second copy of it to fall out of step. The
   * queue wins over both because it is drawn over whatever the player was
   * doing and ○ puts them straight back on it — closing it restores the two
   * search phases without either of them having been touched.
   */
  const gamesPhase: StoreGamesPhase =
    queueOpen ? 'queue' : search.system ? 'results' : 'systems'

  /**
   * Which list the cursor is on, as one value.
   *
   * A tab is a different list, and so is a phase, and so is a new query. All
   * three reset the cursor, and they are one key rather than three effects
   * because of what the second one has to beat: the clamp below, which pulls
   * the cursor back onto the last row that exists. Written as separate
   * effects, switching to a shorter list ran BOTH — the reset to 0 and then
   * the clamp to the end of the new list, which won by being declared second
   * and left the cursor on the last row of a tab the player had just opened.
   */
  const listKey = `${tab}:${gamesPhase}:${search.query}`
  const lastListKey = useRef(listKey)

  /**
   * The list under the cursor, and the shape it is paged in.
   *
   * One cursor for all three lists rather than one per tab: the d-pad handlers
   * below read a count and a page size, and giving them three of each is how a
   * page turn on one list starts reading the length of another.
   */
  const games = gamesPhase === 'queue' ? jobs.jobs
    : gamesPhase === 'results' ? search.results
      : gamesSystems
  const items: (CatalogEntry | StoreSearchResult | StoreJob)[] =
    tab === 'consoles' ? consoles : games
  // A queue row is a line of text like a result is, so it is paged the same
  // way — one column of rows, not a 4 × 3 grid of truncated names.
  const asRows = tab === 'games' && gamesPhase !== 'systems'
  const cols = asRows ? 1 : COLS
  const rows = asRows ? RESULT_ROWS : ROWS
  const perPage = cols * rows
  const totalItems = items.length
  const pageCount = Math.ceil(totalItems / perPage)
  // `page` belongs to whichever list the cursor is on, so the Consoles tab's
  // own slice reads it only while that tab is the one open. Otherwise it would
  // be indexing the catalogue with the results list's page number, and a view
  // reading `pageItems` from the Games tab would get whatever that landed on.
  const consolePage = tab === 'consoles' ? page : 0
  const pageItems = consoles.slice(consolePage * PER_PAGE, (consolePage + 1) * PER_PAGE)
  const gamesSystemsPage = gamesSystems.slice(page * perPage, (page + 1) * perPage)
  const gamesResultsPage = search.results.slice(page * perPage, (page + 1) * perPage)
  const gamesJobsPage = jobs.jobs.slice(page * perPage, (page + 1) * perPage)

  // The live read the handlers take; see the declarations above.
  consolesRef.current = consoles
  focusRef.current = focusIdx
  pageRef.current = page
  countRef.current = totalItems
  pageCountRef.current = pageCount
  tabRef.current = tab
  itemsRef.current = items
  colsRef.current = cols
  rowsRef.current = rows
  perPageRef.current = perPage
  phaseRef.current = gamesPhase
  showSearchRef.current = showSearch

  useEffect(() => {
    const id = keepFocusOn.current
    if (!id) return
    keepFocusOn.current = null
    const at = consoles.findIndex(c => c.id === id)
    if (at < 0) return
    setPage(Math.floor(at / PER_PAGE))
    setFocusIdx(at % PER_PAGE)
  }, [consoles])

  /**
   * A new list starts at the top; the list it already had is only clamped.
   *
   * The clamp is for a list that came back shorter than where the cursor was —
   * remove the last pack, or run a search that answers fewer rows than the
   * last one, and the index points past the end, which reads as the highlight
   * vanishing rather than as a list that changed.
   *
   * The two are one effect so that the order between them is stated rather
   * than inherited from the order they happen to be declared in. See
   * `listKey`: that ordering was a bug before it was a rule.
   */
  const heldNow = Math.max(0, Math.min(perPage, totalItems - page * perPage))
  useEffect(() => {
    if (lastListKey.current !== listKey) {
      lastListKey.current = listKey
      setPage(0)
      setFocusIdx(0)
      return
    }
    if (pageCount > 0 && page > pageCount - 1) setPage(pageCount - 1)
    else if (heldNow > 0 && focusIdx > heldNow - 1) setFocusIdx(heldNow - 1)
  }, [listKey, pageCount, page, heldNow, focusIdx])

  // `omit` is a prop and a fresh array on every parent render; the effect below
  // only cares whether an id is in it.
  const omitNav = !!omit?.includes('nav')
  const omitTabs = !!omit?.includes('tabs')
  const omitActions = !!omit?.includes('actions')

  useEffect(() => {
    /**
     * Nothing on this screen may act at all.
     *
     * Split from `blocked()` below when the asked-about panel gained an
     * action. The panel takes the cursor out of play — it is a detail view
     * over the list — but ✕ on it now means something, so "the cursor holds
     * still" and "no button does anything" stopped being the same sentence
     * and had to stop being the same function.
     */
    const closed = () =>
      screenRef.current !== 'store' ||
      modalDepthRef.current > 0 ||
      // The keyboard has its own d-pad and its own ✕. Without this the grid
      // underneath walks along with the letters, and ✕ picks a console while
      // the player is spelling a title.
      showSearchRef.current ||
      useStore.getState().sessionGameKey !== null

    const blocked = () =>
      closed() ||
      // The panel an asked-about result opens over the list is a detail view,
      // so the cursor under it holds still and ○ is the way out. Without this,
      // navigating on it silently moves the invisible cursor underneath.
      (tabRef.current === 'games' && !!searchRef.current.asked)

    /** How many cards this page actually holds — the last one is usually short. */
    const held = () =>
      Math.max(0, Math.min(perPageRef.current,
                           countRef.current - pageRef.current * perPageRef.current))

    /** Whatever the cursor is on: a pack on two of the four lists, a search
     *  result on the third, a queued job on the fourth. */
    const focused = () =>
      itemsRef.current[pageRef.current * perPageRef.current + focusRef.current]

    /** The pack under the cursor on the Consoles tab — the only list whose
     *  rows are packs that `useCatalog` may be handed. The Games tab's
     *  handlers return before this is reached. */
    const focusedPack = (): CatalogEntry | undefined =>
      tabRef.current === 'consoles' ? focused() as CatalogEntry | undefined : undefined

    /**
     * Queue what the asked-about panel is showing, then show the queue.
     *
     * Stepping to the queue is the point of the second half: the press wrote a
     * row, and a screen that stayed on the panel would have given the player
     * no evidence of it — which is exactly how the previous version of this
     * button, the one that recorded a choice nothing acted on, came to read as
     * a button that does nothing.
     *
     * The panel is put down whether or not the request succeeded, and the
     * refusal is carried by `useStoreJobs` as `actionError`: the failures are
     * "already in the queue" and "the queue is full", and both are answered by
     * looking at the queue.
     */
    const queueAsked = async (result: StoreSearchResult) => {
      const job = await jobsRef.current.queue(result)
      searchRef.current.unask()
      if (job) setQueueOpen(true)
    }

    const navigate = (dir: 'up' | 'down' | 'left' | 'right') => {
      if (blocked()) return
      // Stepping away from an armed removal is how a player says no, and it is
      // the whole reason the second press is safe to offer.
      catalogRef.current.disarm()
      const focus = focusRef.current
      const at = pageRef.current
      const onPage = held()
      const pages = pageCountRef.current
      // The shape of the list under the cursor, not the grid's: the results
      // list is one column, and walking it with COLS = 4 would step four rows
      // at a time and page at the wrong place.
      const COLS = colsRef.current
      const ROWS = rowsRef.current
      const PER_PAGE = perPageRef.current
      const col = focus % COLS
      const row = Math.floor(focus / COLS)
      /** Last valid index on a page — pages can be partially filled. */
      const lastOf = (p: number) => Math.min(PER_PAGE, countRef.current - p * PER_PAGE) - 1
      const to = (p: number, i: number) => { setPage(p); setFocusIdx(Math.max(0, i)) }

      // Running off the end of a row turns the page rather than stopping dead.
      // That is the behaviour the seam exists to keep identical everywhere: a
      // themed screen that reimplemented it got it subtly wrong every time.
      if (dir === 'right') {
        if (col < COLS - 1 && focus < onPage - 1) setFocusIdx(focus + 1)
        else if (at < pages - 1) to(at + 1, Math.min(row * COLS, lastOf(at + 1)))
      } else if (dir === 'left') {
        if (col > 0) setFocusIdx(focus - 1)
        else if (at > 0) to(at - 1, Math.min(row * COLS + COLS - 1, lastOf(at - 1)))
      } else if (dir === 'down') {
        const next = focus + COLS
        if (next < onPage) setFocusIdx(next)
        else if (at < pages - 1) to(at + 1, Math.min(col, lastOf(at + 1)))
      } else if (dir === 'up') {
        if (row > 0) setFocusIdx(focus - COLS)
        else if (at > 0) to(at - 1, Math.min((ROWS - 1) * COLS + col, lastOf(at - 1)))
      }
    }

    const stepTab = (delta: number) => {
      if (blocked()) return
      catalogRef.current.disarm()
      const i = STORE_TABS.indexOf(tabRef.current)
      setTab(STORE_TABS[(i + delta + STORE_TABS.length) % STORE_TABS.length])
    }

    const offs = [
      ...(omitNav ? [] : [
        onGp('gp:dpad-up', () => navigate('up')),
        onGp('gp:dpad-down', () => navigate('down')),
        onGp('gp:dpad-left', () => navigate('left')),
        onGp('gp:dpad-right', () => navigate('right')),
      ]),
      /**
       * L1/R1 walk the tabs, and the d-pad's own edges turn the pages.
       *
       * The dashboard binds the shoulders to paging and this screen cannot:
       * the two tabs are the whole shape of it, and a screen whose headline
       * gesture had no button would be a screen reachable only with a mouse
       * the box does not have. Paging loses nothing by it — running off the
       * right of the last column already turns the page, on the dashboard too.
       */
      ...(omitTabs ? [] : [
        onGp('gp:l1', () => stepTab(-1)),
        onGp('gp:r1', () => stepTab(1)),
      ]),
      /**
       * ✕ installs, and removes on the second press. △ reconfigures.
       *
       * △ and not □: □ is the controller screen and the shell binds it with no
       * guard at all, so a store that took it would be a store you cannot test
       * a pad from. △ is free here — the shell's own △ is guarded to the
       * dashboard, which is the screen it opens this one FROM.
       *
       * Both go through `useCatalog`, which holds every card while a run is in
       * flight and asks twice before a removal. Neither rule is restated here:
       * a second copy of "is anything running" is how the two settings pages
       * came to disagree about it.
       *
       * On the Games tab the same two buttons mean the tab's own two steps:
       * ✕ picks the console and then asks about a result, △ opens the
       * keyboard. Nothing there installs or removes anything, so neither goes
       * near `useCatalog`.
       */
      ...(omitActions ? [] : [
        onGp('gp:confirm', () => {
          if (closed()) return
          if (tabRef.current === 'games') {
            // The asked-about panel first, because it is the one place the
            // cursor is out of play and the button still means something:
            // ✕ on it queues what the player is reading about.
            const asked = searchRef.current.asked
            if (asked) { void queueAsked(asked); return }
            if (blocked()) return
            const row = focused()
            if (!row) return
            if (phaseRef.current === 'systems') {
              // Picking the console is picking it AND asking what for: a
              // console with nothing typed into it has nothing to show, so
              // the keyboard opens with it rather than after another press.
              searchRef.current.choose(row as CatalogEntry)
              setShowSearch(true)
            } else if (phaseRef.current === 'queue') {
              // Stop it. A no-op on a finished row, decided by `useStoreJobs`
              // rather than here: ✕ lands wherever the cursor happens to be,
              // and a finished job answering 409 would be an error the player
              // did not cause.
              void jobsRef.current.cancel(row as StoreJob)
            } else {
              searchRef.current.ask(row as StoreSearchResult)
            }
            return
          }
          if (blocked()) return
          const pack = focusedPack()
          if (pack) void catalogRef.current.act(pack)
        }),
        onGp('gp:y', () => {
          if (blocked()) return
          if (tabRef.current === 'games') {
            // Search again, in the console already chosen. The library binds
            // △ to its search for the same reason, and a player who has used
            // one has used the other.
            if (phaseRef.current === 'results') setShowSearch(true)
            // And from the console list it opens the queue, which is the only
            // free button left on this tab: ✕ picks and asks, ○ leaves, L1/R1
            // walk the tabs, and □ is the shell's controller screen, bound
            // with no guard at all.
            else if (phaseRef.current === 'systems') setQueueOpen(true)
            return
          }
          const pack = focusedPack()
          if (pack) void catalogRef.current.reconfigure(pack)
        }),
      ]),
      /**
       * ○ goes home, and stays with the host whatever a theme declares.
       *
       * The same rule as the library's: a store is a place the player has to
       * be able to leave, and a theme that took this button and forgot to
       * offer the way out would strand them on it. `modalDepth` rather than
       * `blocked()`, so leaving still works while a game is suspended in the
       * background — the session bar is on screen then, and the Store is not
       * where the player wants to be.
       *
       * It steps back through the Games tab before it leaves, which is the
       * library's shape too: the queue, then an asked result, then the
       * console, then home. The exception the library also makes is the
       * keyboard — it is on top, so ○ closes that first and the screen
       * underneath does not move.
       */
      onGp('gp:back', () => {
        if (screenRef.current !== 'store') return
        if (showSearchRef.current) { setShowSearch(false); return }
        if (modalDepthRef.current > 0) return
        if (tabRef.current === 'games') {
          // The queue is on top of everything, so it closes first — and it
          // closes onto whatever was underneath, which is why it is its own
          // flag rather than a state of the search.
          if (phaseRef.current === 'queue') { setQueueOpen(false); return }
          if (searchRef.current.asked) { searchRef.current.unask(); return }
          if (phaseRef.current === 'results') { searchRef.current.leave(); return }
        }
        goHome()
      }),
    ]
    return () => offs.forEach(off => off())
    // Registered once, for the life of the screen. Every value the handlers
    // need is read live above — a dependency list that changed on each step
    // would tear the listeners down and rebuild them on every press, which is
    // both the stale-cursor bug and needless work per frame.
  }, [omitNav, omitTabs, omitActions, goHome])

  return (
    <>
      <View
        tab={tab}
        tabs={STORE_TABS}
        tabLabels={STORE_TAB_LABELS}
        consoles={consoles}
        pageItems={pageItems}
        focusIdx={focusIdx}
        page={page}
        pageCount={pageCount}
        cols={cols}
        rows={rows}
        perPage={perPage}
        installedCount={consoles.filter((c: CatalogEntry) => c.installed).length}
        loading={catalog.loading}
        loadError={catalog.loadFailed}
        workingId={catalog.workingId}
        busy={catalog.busy}
        armedId={catalog.armedId}
        log={catalog.log}
        actionError={catalog.actionError}
        // Searching is here. Downloading is not, and the two are separate
        // flags so a view can draw results without promising a download.
        gamesReady
        gamesPhase={gamesPhase}
        gamesSystems={gamesSystems}
        gamesSystemsPage={gamesSystemsPage}
        gamesSystem={search.system}
        gamesQuery={search.query}
        gamesResults={search.results}
        gamesResultsPage={gamesResultsPage}
        gamesLoading={search.loading}
        gamesError={search.error}
        gamesAnswered={search.answered}
        gamesLive={search.live}
        gamesProvider={search.providerLabel}
        gamesRomsDir={search.romsDir}
        gamesAsked={search.asked}
        // Read from the backend rather than written here, and still false:
        // a job is a real row that a worker really runs, but nothing is behind
        // that worker, so no byte lands in a ROM directory. See the contract.
        gamesDownloadReady={jobs.downloadReady}
        gamesJobs={jobs.jobs}
        gamesJobsPage={gamesJobsPage}
        gamesJobsLive={jobs.liveCount}
        gamesJobsError={jobs.error}
        gamesQueueing={jobs.queueing}
        gamesQueueError={jobs.actionError}
        onTab={setTab}
        onFocus={setFocusIdx}
        onPage={(p) => { setPage(p); setFocusIdx(0) }}
        onBack={goHome}
        onRetry={() => void catalog.load()}
        onAct={(pack) => void catalog.act(pack)}
        onReconfigure={(pack) => void catalog.reconfigure(pack)}
        onGamesSystem={(system) => { search.choose(system); setShowSearch(true) }}
        onGamesSearch={() => setShowSearch(true)}
        onGamesAsk={(result) => search.ask(result)}
        onGamesQueue={(result) => {
          void jobs.queue(result).then(job => {
            search.unask()
            if (job) setQueueOpen(true)
          })
        }}
        onGamesQueueOpen={() => setQueueOpen(true)}
        onGamesCancelJob={(job) => void jobs.cancel(job)}
        onGamesBack={() => {
          if (queueOpen) setQueueOpen(false)
          else if (search.asked) search.unask()
          else if (search.system) search.leave()
        }}
      />

      {/* The host's, not the view's — the same rule and the same reason as the
          library's: a themed store cannot ship without a way to type, and the
          keyboard is what registers as a modal so the global shortcuts stand
          down over it. */}
      <AnimatePresence>
        {showSearch && (
          <Overlay onClose={() => setShowSearch(false)}>
            <VirtualKeyboard
              className="gc-search-kb"
              title={search.system ? `Search ${search.system.label}` : 'Search'}
              initialValue={search.query}
              placeholder="search a game…"
              onConfirm={val => {
                setShowSearch(false)
                void search.run(val)
              }}
              // Cancelling out of the first search leaves the console chosen
              // and nothing searched for, which is a screen with an empty
              // list and no way to read it as anything but empty. So it steps
              // back to the consoles instead — unless a search has already
              // answered, in which case there is something to go back TO.
              onCancel={() => {
                setShowSearch(false)
                if (!searchRef.current.answered) searchRef.current.leave()
              }}
            />
          </Overlay>
        )}
      </AnimatePresence>
    </>
  )
}
