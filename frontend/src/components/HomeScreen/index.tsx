/**
 * HomeScreen — grid carousel.
 *
 * Layout: COLS × ROWS cards per page.
 * Navigating past the last column slides to the next page.
 * Mouse hover also works independently of gamepad focus.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { motion } from 'framer-motion'
import { useStore } from '../../store'
import { api, SystemEntry, PlaytimeEntry } from '../../api'
import { onGp } from '../../hooks/useGamepad'
import { onWsEvent } from '../../hooks/useWebSocket'
import SystemCard from './SystemCard'

const COLS = 4
const ROWS = 2
const PER_PAGE = COLS * ROWS

interface Props {
  onLaunchApp: (system: SystemEntry) => void
}

export default function HomeScreen({ onLaunchApp }: Props) {
  const { goLibrary, gridFocusIdx, gridPage, setGridFocus, setGridPage, modalDepth, screen } = useStore()

  // Always-fresh refs so gamepad closures don't go stale
  const modalDepthRef = useRef(modalDepth)
  const screenRef = useRef(screen)
  useEffect(() => { modalDepthRef.current = modalDepth }, [modalDepth])
  useEffect(() => { screenRef.current = screen }, [screen])
  const [systems, setSystems] = useState<SystemEntry[]>([])
  const [playtimeMap, setPlaytimeMap] = useState<Record<string, PlaytimeEntry>>({})
  const [gameCountMap, setGameCountMap] = useState<Record<string, number>>({})
  const totalItems = systems.length
  const pageCount = Math.ceil(totalItems / PER_PAGE)
  const pageItems = systems.slice(gridPage * PER_PAGE, (gridPage + 1) * PER_PAGE)
  const globalIdx = gridPage * PER_PAGE + gridFocusIdx

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
    (p: number) => Math.min(PER_PAGE, totalItems - p * PER_PAGE) - 1,
    [totalItems],
  )

  // Safety: if the grid shrinks (or state was persisted), keep focus on a real card
  useEffect(() => {
    if (pageCount > 0 && gridPage > pageCount - 1) setGridPage(pageCount - 1)
    else if (pageItems.length > 0 && gridFocusIdx > pageItems.length - 1) setGridFocus(pageItems.length - 1)
  }, [pageCount, gridPage, pageItems.length, gridFocusIdx, setGridPage, setGridFocus])

  const navigate = useCallback((dir: 'up' | 'down' | 'left' | 'right') => {
    const col = gridFocusIdx % COLS
    const row = Math.floor(gridFocusIdx / COLS)

    if (dir === 'right') {
      if (col < COLS - 1 && gridFocusIdx < pageItems.length - 1) {
        setGridFocus(gridFocusIdx + 1)
      } else if (gridPage < pageCount - 1) {
        setGridPage(gridPage + 1)
        setGridFocus(Math.min(row * COLS, lastIdxOf(gridPage + 1)))
      }
    } else if (dir === 'left') {
      if (col > 0) {
        setGridFocus(gridFocusIdx - 1)
      } else if (gridPage > 0) {
        setGridPage(gridPage - 1)
        setGridFocus(Math.min(row * COLS + COLS - 1, lastIdxOf(gridPage - 1)))
      }
    } else if (dir === 'down') {
      const next = gridFocusIdx + COLS
      if (next < pageItems.length) {
        setGridFocus(next)
      } else if (gridPage < pageCount - 1) {
        setGridPage(gridPage + 1)
        setGridFocus(Math.min(col, lastIdxOf(gridPage + 1)))
      }
    } else if (dir === 'up') {
      if (row > 0) {
        setGridFocus(gridFocusIdx - COLS)
      } else if (gridPage > 0) {
        setGridPage(gridPage - 1)
        setGridFocus(Math.min((ROWS - 1) * COLS + col, lastIdxOf(gridPage - 1)))
      }
    }
  }, [gridFocusIdx, gridPage, pageCount, pageItems.length, lastIdxOf, setGridFocus, setGridPage])

  const activate = useCallback(() => {
    const system = pageItems[gridFocusIdx]
    if (!system) return
    if (system.kind === 'app' || system.type === 'application') {
      onLaunchApp(system)
    } else {
      goLibrary(system.id)
    }
  }, [pageItems, gridFocusIdx, goLibrary, onLaunchApp])

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
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', padding: '28px 48px', overflowY: 'auto',
      position: 'relative',
    }}>
      {/* Stats */}
      <div style={{ marginBottom: 32, textAlign: 'center' }}>
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.25)', letterSpacing: 3, marginBottom: 10 }}>
          YOUR LIBRARY
        </div>
        <div style={{ display: 'flex', gap: 36, justifyContent: 'center' }}>
          {[
            { v: systems.filter(s => s.kind === 'emulator' || s.type === 'emulator').length, l: 'Systems' },
            { v: totalGames, l: 'Games' },
            { v: `${totalHours}h`, l: 'Played' },
          ].map(s => (
            <div key={s.l} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 26, fontWeight: 800, color: '#c4b5fd' }}>{s.v}</div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', letterSpacing: 1, marginTop: 2 }}>{s.l}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Grid carousel */}
      <div style={{ width: '100%', maxWidth: 960, position: 'relative' }}>
        {/* Prev page arrow */}
        {gridPage > 0 && (
          <button
            onClick={() => { setGridPage(gridPage - 1); setGridFocus(0) }}
            style={{
              position: 'absolute', left: -44, top: '50%', transform: 'translateY(-50%)',
              width: 36, height: 36, borderRadius: '50%', border: '1px solid rgba(255,255,255,0.12)',
              background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.6)',
              fontSize: 22, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
              zIndex: 2, transition: 'all 0.15s',
            }}
          >‹</button>
        )}

        {/* Next page arrow */}
        {gridPage < pageCount - 1 && (
          <button
            onClick={() => { setGridPage(gridPage + 1); setGridFocus(0) }}
            style={{
              position: 'absolute', right: -44, top: '50%', transform: 'translateY(-50%)',
              width: 36, height: 36, borderRadius: '50%', border: '1px solid rgba(255,255,255,0.12)',
              background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.6)',
              fontSize: 22, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
              zIndex: 2, transition: 'all 0.15s',
            }}
          >›</button>
        )}

        <div style={{ overflow: 'hidden', width: '100%', willChange: 'transform' }}>
          <motion.div
            animate={{ x: pageCount > 1 ? `${-(gridPage / pageCount) * 100}%` : 0 }}
            transition={{ type: 'spring', stiffness: 280, damping: 30, clamp: true }}
            style={{ display: 'flex', width: `${Math.max(pageCount, 1) * 100}%` }}
          >
            {Array.from({ length: Math.max(pageCount, 1) }).map((_, pi) => (
              <div key={pi} style={{
                width: `${100 / Math.max(pageCount, 1)}%`, flexShrink: 0,
                display: 'grid', gridTemplateColumns: `repeat(${COLS}, 1fr)`,
                gridTemplateRows: `repeat(${ROWS}, 1fr)`, alignContent: 'start', gap: 12,
              }}>
                {systems.slice(pi * PER_PAGE, (pi + 1) * PER_PAGE).map((system, i) => (
                  <SystemCard
                    key={system.id}
                    system={system}
                    playtime={playtimeMap[system.id]}
                    gameCount={gameCountMap[system.id]}
                    focused={pi === gridPage && i === gridFocusIdx}
                    onClick={() => {
                      setGridFocus(i)
                      if (system.kind === 'app' || system.type === 'application') {
                        onLaunchApp(system)
                      } else {
                        goLibrary(system.id)
                      }
                    }}
                  />
                ))}
              </div>
            ))}
          </motion.div>
        </div>
      </div>

      {/* Page indicator */}
      {pageCount > 1 && (
        <div style={{ display: 'flex', gap: 6, marginTop: 24 }}>
          {Array.from({ length: pageCount }).map((_, i) => (
            <div
              key={i}
              onClick={() => { setGridPage(i); setGridFocus(0) }}
              style={{
                width: i === gridPage ? 20 : 6, height: 6, borderRadius: 3, cursor: 'pointer',
                background: i === gridPage ? '#7c3aed' : 'rgba(255,255,255,0.15)',
                transition: 'all 0.3s',
              }}
            />
          ))}
        </div>
      )}

      {/* Gamepad hint */}
      <div style={{ marginTop: 16, fontSize: 11, color: 'rgba(255,255,255,0.15)', letterSpacing: 1 }}>
        {pageCount > 1 ? '← → Navigate · L1/R1 Page · ✕ Select' : '← → Navigate · ✕ Select'}
      </div>
    </div>
  )
}
