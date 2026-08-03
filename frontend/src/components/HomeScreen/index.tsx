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
  const { goLibrary, gridFocusIdx, gridPage, setGridFocus, setGridPage, modalDepth, screen } = useStore()

  // A theme may ask for a different grid — one long row of big icons, say.
  // The navigation below is unchanged and still owns paging, focus and wrap:
  // only the shape it walks is negotiable, because the shape is layout and
  // layout is the theme's side of the line. The backend has already bounded
  // these (services/themes._home_grid); the `||` is for a theme that names
  // only one of the two.
  const themeHome = useThemeCtx()?.manifest?.home
  const cols = themeHome?.cols || COLS
  const rows = themeHome?.rows || ROWS
  const perPage = cols * rows

  // Always-fresh refs so gamepad closures don't go stale
  const modalDepthRef = useRef(modalDepth)
  const screenRef = useRef(screen)
  useEffect(() => { modalDepthRef.current = modalDepth }, [modalDepth])
  useEffect(() => { screenRef.current = screen }, [screen])
  const [systems, setSystems] = useState<SystemEntry[]>([])
  const [playtimeMap, setPlaytimeMap] = useState<Record<string, PlaytimeEntry>>({})
  const [gameCountMap, setGameCountMap] = useState<Record<string, number>>({})
  const totalItems = systems.length
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

  const navigate = useCallback((dir: 'up' | 'down' | 'left' | 'right') => {
    const col = gridFocusIdx % cols
    const row = Math.floor(gridFocusIdx / cols)

    if (dir === 'right') {
      if (col < cols - 1 && gridFocusIdx < pageItems.length - 1) {
        setGridFocus(gridFocusIdx + 1)
      } else if (gridPage < pageCount - 1) {
        setGridPage(gridPage + 1)
        setGridFocus(Math.min(row * cols, lastIdxOf(gridPage + 1)))
      }
    } else if (dir === 'left') {
      if (col > 0) {
        setGridFocus(gridFocusIdx - 1)
      } else if (gridPage > 0) {
        setGridPage(gridPage - 1)
        setGridFocus(Math.min(row * cols + cols - 1, lastIdxOf(gridPage - 1)))
      }
    } else if (dir === 'down') {
      const next = gridFocusIdx + cols
      if (next < pageItems.length) {
        setGridFocus(next)
      } else if (gridPage < pageCount - 1) {
        setGridPage(gridPage + 1)
        setGridFocus(Math.min(col, lastIdxOf(gridPage + 1)))
      }
    } else if (dir === 'up') {
      if (row > 0) {
        setGridFocus(gridFocusIdx - cols)
      } else if (gridPage > 0) {
        setGridPage(gridPage - 1)
        setGridFocus(Math.min((rows - 1) * cols + col, lastIdxOf(gridPage - 1)))
      }
    }
  }, [gridFocusIdx, gridPage, pageCount, pageItems.length, lastIdxOf, setGridFocus, setGridPage, cols, rows])

  /** Opens a card; defaults to the focused one, so the pad and the mouse agree. */
  const activate = useCallback((idx: number = gridFocusIdx) => {
    const system = pageItems[idx]
    if (!system) return
    if (idx !== gridFocusIdx) setGridFocus(idx)
    if (system.kind === 'app' || system.type === 'application') {
      onLaunchApp(system)
    } else {
      goLibrary(system.id)
    }
  }, [pageItems, gridFocusIdx, setGridFocus, goLibrary, onLaunchApp])

  // Gamepad events — all guarded so they don't fire when a modal is open
  useEffect(() => {
    const blocked = () => screenRef.current !== 'home' || modalDepthRef.current > 0
    const offs = [
      onGp('gp:dpad-up',    () => { if (blocked()) return; navigate('up') }),
      onGp('gp:dpad-down',  () => { if (blocked()) return; navigate('down') }),
      onGp('gp:dpad-left',  () => { if (blocked()) return; navigate('left') }),
      onGp('gp:dpad-right', () => { if (blocked()) return; navigate('right') }),
      onGp('gp:r1',  () => { if (blocked()) return; if (gridPage < pageCount - 1) { setGridPage(gridPage + 1); setGridFocus(0) } }),
      onGp('gp:l1',  () => { if (blocked()) return; if (gridPage > 0) { setGridPage(gridPage - 1); setGridFocus(0) } }),
      onGp('gp:confirm', () => { if (blocked()) return; activate() }),
    ]
    return () => offs.forEach(off => off())
  }, [navigate, activate, gridPage, pageCount, setGridPage, setGridFocus])

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
