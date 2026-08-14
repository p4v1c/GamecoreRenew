/**
 * HomeScreen — the dashboard's behaviour.
 *
 * Layout: cols × rows cards per page — 4 × 2 unless the active theme's
 * manifest asks for something else (`home: { cols, rows }`). The shape is
 * negotiable because it is layout; the rules below are not.
 * Navigating past the last column slides to the next page.
 * Mouse hover also works independently of gamepad focus.
 *
 * The markup lives in a view component, default or themed. This file is what
 * guarantees they behave identically: the paging rules, the gamepad bindings
 * and the launching are here, and a theme cannot replace them.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useStore } from '../../store'
import { api, SystemEntry, PlaytimeEntry } from '../../api'
import { onGp } from '../../hooks/useGamepad'
import { onWsEvent } from '../../hooks/useWebSocket'
import DefaultHomeView from './DefaultHomeView'
import { useThemeCtx } from '../ThemeSurface'
import type { HomeViewProps } from './types'

// What the dashboard is when nobody asks for anything else — the default UI
// and every theme written before `home` existed.
const COLS = 4
const ROWS = 2

interface Props {
  onLaunchApp: (system: SystemEntry) => void
  view?: React.ComponentType<HomeViewProps>
}

export default function HomeScreen({ onLaunchApp, view: View = DefaultHomeView }: Props) {
  // One subscription per value. A bare `useStore()` subscribes to every field,
  // so this screen re-rendered on `selectedGameIdx` — a value it does not read
  // and cannot show — for every step the player took in the library, while it
  // was hidden behind it. Same in DefaultShell, and see shellRerender.test.tsx.
  const goLibrary = useStore(s => s.goLibrary)
  const gridFocusIdx = useStore(s => s.gridFocusIdx)
  const gridPage = useStore(s => s.gridPage)
  const setGridFocus = useStore(s => s.setGridFocus)
  const setGridPage = useStore(s => s.setGridPage)
  const modalDepth = useStore(s => s.modalDepth)
  const screen = useStore(s => s.screen)

  // A theme may ask for a different grid — one long row of big icons, say.
  // The navigation below is unchanged and still owns paging, focus and wrap:
  // only the shape it walks is negotiable, because the shape is layout and
  // layout is the theme's side of the line. The backend has already bounded
  // these (services/themes._home_grid); the `||` is for a theme that names
  // only one of the two.
  const themeHome = useThemeCtx()?.manifest?.home

  // Always-fresh refs so gamepad closures don't go stale
  const modalDepthRef = useRef(modalDepth)
  const screenRef = useRef(screen)
  useEffect(() => { modalDepthRef.current = modalDepth }, [modalDepth])
  useEffect(() => { screenRef.current = screen }, [screen])
  const [systems, setSystems] = useState<SystemEntry[]>([])
  const [playtimeMap, setPlaytimeMap] = useState<Record<string, PlaytimeEntry>>({})
  const [gameCountMap, setGameCountMap] = useState<Record<string, number>>({})
  const totalItems = systems.length

  const rows = themeHome?.rows || ROWS
  // A theme can also ask for no pages at all. `cols` then follows the list
  // instead of the list following `cols`: one page holds everything, pageCount
  // is 1, and L1/R1 have nowhere to go — which is the point. A number in the
  // manifest could not do this; it would be right until the seventeenth system.
  const cols = themeHome?.paged === false
    ? Math.max(1, Math.ceil(totalItems / rows))
    : (themeHome?.cols || COLS)
  const perPage = cols * rows

  const pageCount = Math.ceil(totalItems / perPage)
  const pageItems = systems.slice(gridPage * perPage, (gridPage + 1) * perPage)

  const loadSystems = useCallback(() => {
    api.systems.list().then(setSystems).catch(console.error)
    api.playtime.all().then(rows => {
      const map: Record<string, PlaytimeEntry> = {}
      rows.forEach(r => {
        if (!map[r.system_id]) {
          map[r.system_id] = { ...r, total_secs: 0 }
        }
        map[r.system_id].total_secs += (r.total_secs || 0)
        if (r.last_played && (!map[r.system_id].last_played || r.last_played > map[r.system_id].last_played!)) {
          map[r.system_id].last_played = r.last_played
        }
      })
      setPlaytimeMap(map)
    }).catch(() => {})
  }, [])

  // Load systems on mount
  useEffect(() => { loadSystems() }, [loadSystems])

  // Re-fetch when home screen becomes visible with empty systems (e.g. after backend restart)
  useEffect(() => {
    if (screen === 'home' && systems.length === 0) {
      loadSystems()
    }
  }, [screen, systems.length, loadSystems])

  // Load game counts lazily
  useEffect(() => {
    systems.forEach(s => {
      if (s.kind === 'emulator' || s.type === 'emulator') {
        api.games.list(s.id).then(games => {
          setGameCountMap(prev => ({ ...prev, [s.id]: games.length }))
        }).catch(() => {})
      }
    })
  }, [systems])

  // Update counts on ROM upload event
  useEffect(() => {
    return onWsEvent('rom_uploaded', (data) => {
      const systemId = data.system_id as string
      if (systemId) {
        api.games.list(systemId).then(games => {
          setGameCountMap(prev => ({ ...prev, [systemId]: games.length }))
        }).catch(() => {})
      }
    })
  }, [])

  // Last valid focus index on a given page (pages can be partially filled)
  const lastIdxOf = useCallback(
    (p: number) => Math.min(perPage, totalItems - p * perPage) - 1,
    [totalItems, perPage],
  )

  // Safety: if the grid shrinks (or state was persisted), keep focus on a real card
  useEffect(() => {
    if (pageCount > 0 && gridPage > pageCount - 1) setGridPage(pageCount - 1)
    else if (pageItems.length > 0 && gridFocusIdx > pageItems.length - 1) setGridFocus(pageItems.length - 1)
  }, [pageCount, gridPage, pageItems.length, gridFocusIdx, setGridPage, setGridFocus])

  // The list itself, live. The cards on a page are a slice of it, and which
  // slice is a question only the CURRENT page can answer — see below.
  const systemsRef = useRef(systems)
  systemsRef.current = systems

  /**
   * Where the cursor is, at the moment a button is pressed.
   *
   * Not where it was when the handler was registered. The d-pad is
   * edge-triggered, so a fast player sends several events before React has
   * re-rendered, and every one of them computed its destination from the same
   * stale focus and page — setting the same index again, which is a no-op.
   * Three taps moved one card. `set()` is synchronous, so reading the store is
   * always the truth, whether or not React has caught up.
   *
   * The page has to be read here too, not just the focus: past the last column
   * a step is a page turn, and a second step arriving on the old page turned
   * the same page twice to the same place. See homeBurst.test.tsx, and
   * LibraryScreen for the same fix on the shelf.
   */
  const cursor = () => {
    const { gridFocusIdx: focus, gridPage: page } = useStore.getState()
    // How many cards this page actually holds — the last one is usually short.
    const onPage = Math.max(0, Math.min(perPage, systemsRef.current.length - page * perPage))
    return { focus, page, onPage }
  }

  const navigate = useCallback((dir: 'up' | 'down' | 'left' | 'right') => {
    const { focus, page, onPage } = cursor()
    const col = focus % cols
    const row = Math.floor(focus / cols)

    if (dir === 'right') {
      if (col < cols - 1 && focus < onPage - 1) {
        setGridFocus(focus + 1)
      } else if (page < pageCount - 1) {
        setGridPage(page + 1)
        setGridFocus(Math.min(row * cols, lastIdxOf(page + 1)))
      }
    } else if (dir === 'left') {
      if (col > 0) {
        setGridFocus(focus - 1)
      } else if (page > 0) {
        setGridPage(page - 1)
        setGridFocus(Math.min(row * cols + cols - 1, lastIdxOf(page - 1)))
      }
    } else if (dir === 'down') {
      const next = focus + cols
      if (next < onPage) {
        setGridFocus(next)
      } else if (page < pageCount - 1) {
        setGridPage(page + 1)
        setGridFocus(Math.min(col, lastIdxOf(page + 1)))
      }
    } else if (dir === 'up') {
      if (row > 0) {
        setGridFocus(focus - cols)
      } else if (page > 0) {
        setGridPage(page - 1)
        setGridFocus(Math.min((rows - 1) * cols + col, lastIdxOf(page - 1)))
      }
    }
  }, [pageCount, perPage, lastIdxOf, setGridFocus, setGridPage, cols, rows]) // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * Opens a card; defaults to the focused one, so the pad and the mouse agree.
   *
   * Also reads live, and here a stale read is not a lost press but a wrong
   * one: the card was resolved out of the page and focus of the last render,
   * so a ✕ arriving in the same window as a move opened the system the player
   * had just left. A mouse click passes its own index and is unaffected.
   */
  const activate = useCallback((idx?: number) => {
    const { focus, page } = cursor()
    const i = idx ?? focus
    const system = systemsRef.current.slice(page * perPage, (page + 1) * perPage)[i]
    if (!system) return
    if (i !== focus) setGridFocus(i)
    if (system.kind === 'app' || system.type === 'application') {
      onLaunchApp(system)
    } else {
      goLibrary(system.id)
    }
  }, [perPage, setGridFocus, goLibrary, onLaunchApp]) // eslint-disable-line react-hooks/exhaustive-deps

  // Gamepad events — all guarded so they don't fire when a modal is open
  useEffect(() => {
    const blocked = () => screenRef.current !== 'home' || modalDepthRef.current > 0
    const offs = [
      onGp('gp:dpad-up',    () => { if (blocked()) return; navigate('up') }),
      onGp('gp:dpad-down',  () => { if (blocked()) return; navigate('down') }),
      onGp('gp:dpad-left',  () => { if (blocked()) return; navigate('left') }),
      onGp('gp:dpad-right', () => { if (blocked()) return; navigate('right') }),
      // Live for the same reason the d-pad is: three taps on R1 are three
      // pages, and each one has to start from the page the one before landed on.
      onGp('gp:r1',  () => { if (blocked()) return; const p = useStore.getState().gridPage; if (p < pageCount - 1) { setGridPage(p + 1); setGridFocus(0) } }),
      onGp('gp:l1',  () => { if (blocked()) return; const p = useStore.getState().gridPage; if (p > 0) { setGridPage(p - 1); setGridFocus(0) } }),
      onGp('gp:confirm', () => { if (blocked()) return; activate() }),
    ]
    return () => offs.forEach(off => off())
  }, [navigate, activate, pageCount, setGridPage, setGridFocus])

  // Stats
  const totalGames = Object.values(gameCountMap).reduce((a, b) => a + b, 0)
  const totalHours = Math.floor(
    Object.values(playtimeMap).reduce((a, b) => a + b.total_secs, 0) / 3600
  )

  return (
    <View
      systems={systems}
      pageItems={pageItems}
      playtime={playtimeMap}
      counts={gameCountMap}
      focusIdx={gridFocusIdx}
      page={gridPage}
      pageCount={pageCount}
      cols={cols}
      rows={rows}
      perPage={perPage}
      totals={{
        systems: systems.filter(s => s.kind === 'emulator' || s.type === 'emulator').length,
        games: totalGames,
        hours: totalHours,
      }}
      onFocus={setGridFocus}
      onPage={(p) => { setGridPage(p); setGridFocus(0) }}
      onActivate={activate}
    />
  )
}
