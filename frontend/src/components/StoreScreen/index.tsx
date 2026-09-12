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
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { useStore } from '../../store'
import { type CatalogEntry } from '../../api'
import { onGp } from '../../hooks/useGamepad'
import { useCatalog } from '../../lib/catalog'
import DefaultStoreView from './DefaultStoreView'
import { STORE_TABS, STORE_TAB_LABELS, type StoreTab, type StoreViewProps } from './types'

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
      keepFocusOn.current =
        consolesRef.current[pageRef.current * PER_PAGE + focusRef.current]?.id ?? null
    },
  })

  const catalogRef = useRef(catalog)
  catalogRef.current = catalog

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

  // A tab is a different list. Leaving the cursor at card 9 of a tab that has
  // none is a highlight nobody can see.
  useEffect(() => { setFocusIdx(0); setPage(0) }, [tab])

  const items = tab === 'consoles' ? consoles : []
  const totalItems = items.length
  const pageCount = Math.ceil(totalItems / PER_PAGE)
  const pageItems = items.slice(page * PER_PAGE, (page + 1) * PER_PAGE)

  // The live read the handlers take; see the declarations above.
  consolesRef.current = consoles
  focusRef.current = focusIdx
  pageRef.current = page
  countRef.current = totalItems
  pageCountRef.current = pageCount
  tabRef.current = tab

  useEffect(() => {
    const id = keepFocusOn.current
    if (!id) return
    keepFocusOn.current = null
    const at = consoles.findIndex(c => c.id === id)
    if (at < 0) return
    setPage(Math.floor(at / PER_PAGE))
    setFocusIdx(at % PER_PAGE)
  }, [consoles])

  // The list can come back shorter than where the cursor was — remove the last
  // pack and the index points past the end, which reads as the highlight
  // vanishing rather than as a list that changed.
  useEffect(() => {
    if (pageCount > 0 && page > pageCount - 1) setPage(pageCount - 1)
    else if (pageItems.length > 0 && focusIdx > pageItems.length - 1) setFocusIdx(pageItems.length - 1)
  }, [pageCount, page, pageItems.length, focusIdx])

  // `omit` is a prop and a fresh array on every parent render; the effect below
  // only cares whether an id is in it.
  const omitNav = !!omit?.includes('nav')
  const omitTabs = !!omit?.includes('tabs')
  const omitActions = !!omit?.includes('actions')

  useEffect(() => {
    const blocked = () =>
      screenRef.current !== 'store' ||
      modalDepthRef.current > 0 ||
      useStore.getState().sessionGameKey !== null

    /** How many cards this page actually holds — the last one is usually short. */
    const held = () =>
      Math.max(0, Math.min(PER_PAGE, countRef.current - pageRef.current * PER_PAGE))

    /** The pack under the cursor, or nothing — the Games tab has no cards. */
    const focused = (): CatalogEntry | undefined =>
      tabRef.current === 'consoles'
        ? consolesRef.current[pageRef.current * PER_PAGE + focusRef.current]
        : undefined

    const navigate = (dir: 'up' | 'down' | 'left' | 'right') => {
      if (blocked()) return
      // Stepping away from an armed removal is how a player says no, and it is
      // the whole reason the second press is safe to offer.
      catalogRef.current.disarm()
      const focus = focusRef.current
      const at = pageRef.current
      const onPage = held()
      const pages = pageCountRef.current
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
       */
      ...(omitActions ? [] : [
        onGp('gp:confirm', () => {
          if (blocked()) return
          const pack = focused()
          if (pack) void catalogRef.current.act(pack)
        }),
        onGp('gp:y', () => {
          if (blocked()) return
          const pack = focused()
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
       */
      onGp('gp:back', () => {
        if (screenRef.current !== 'store' || modalDepthRef.current > 0) return
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
    <View
      tab={tab}
      tabs={STORE_TABS}
      tabLabels={STORE_TAB_LABELS}
      consoles={consoles}
      pageItems={pageItems}
      focusIdx={focusIdx}
      page={page}
      pageCount={pageCount}
      cols={COLS}
      rows={ROWS}
      perPage={PER_PAGE}
      installedCount={consoles.filter((c: CatalogEntry) => c.installed).length}
      loading={catalog.loading}
      loadError={catalog.loadFailed}
      workingId={catalog.workingId}
      busy={catalog.busy}
      armedId={catalog.armedId}
      log={catalog.log}
      actionError={catalog.actionError}
      // Downloading arrives with the acquisition steps; until then the tab says
      // so rather than drawing a list that is not there.
      gamesReady={false}
      onTab={setTab}
      onFocus={setFocusIdx}
      onPage={(p) => { setPage(p); setFocusIdx(0) }}
      onBack={goHome}
      onRetry={() => void catalog.load()}
      onAct={(pack) => void catalog.act(pack)}
      onReconfigure={(pack) => void catalog.reconfigure(pack)}
    />
  )
}
