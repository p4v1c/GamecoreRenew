import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useStore } from '../../store'
import { api, GameEntry, GameMeta, PlaytimeEntry, SystemEntry } from '../../api'
import { onGp } from '../../hooks/useGamepad'
import { fmtTime, fmtDate, hexToRgb, Chip, Overlay } from '../ui'
import { VirtualKeyboard } from '../ui/VirtualKeyboard'
import { SYSTEM_COLORS } from '../../lib/systemColors'
import { formatGameName } from '../../lib/formatGameName'
import { playSound } from '../../lib/sounds'

type SortKey = 'name' | 'playtime' | 'lastPlayed'

export default function LibraryScreen() {
  const { selectedSystemId, selectedGameIdx, goHome, setSelectedGameIdx, setSession, modalDepth, screen, sessionGameKey } = useStore()
  const modalDepthRef = useRef(modalDepth)
  const screenRef = useRef(screen)
  useEffect(() => { modalDepthRef.current = modalDepth }, [modalDepth])
  useEffect(() => { screenRef.current = screen }, [screen])
  const [system, setSystem] = useState<SystemEntry | null>(null)
  const [games, setGames] = useState<GameEntry[]>([])
  const [playtimeMap, setPlaytimeMap] = useState<Record<string, PlaytimeEntry>>({})
  const [sort, setSort] = useState<SortKey>('name')
  const [search, setSearch] = useState('')
  const [launching, setLaunching] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [showSearch, setShowSearch] = useState(false)

  const showSearchRef = useRef(showSearch)
  useEffect(() => { showSearchRef.current = showSearch }, [showSearch])

  const SORT_KEYS: SortKey[] = ['name', 'playtime', 'lastPlayed']

  const color = (system?.color || SYSTEM_COLORS[selectedSystemId?.toLowerCase() || ''] || '#7c3aed')
  const rgb = hexToRgb(color)

  const loadData = useCallback((systemId: string) => {
    setLoading(true)
    setLoadError(false)
    Promise.all([
      api.systems.get(systemId),
      api.games.list(systemId),
      api.playtime.forSystem(systemId),
    ]).then(([sys, gameList, rows]) => {
      setSystem(sys)
      setGames(gameList)
      const m: Record<string, PlaytimeEntry> = {}
      rows.forEach(r => { m[r.game_key] = r })
      setPlaytimeMap(m)
      setLoadError(false)
    }).catch(err => {
      console.error(err)
      setLoadError(true)
    }).finally(() => setLoading(false))
  }, [])

  // Reset launching state when session changes
  useEffect(() => {
    if (sessionGameKey === null) {
      setLaunching(false)
    }
  }, [sessionGameKey])

  useEffect(() => {
    setSystem(null)
    setGames([])
    setPlaytimeMap({})
    setSearch('')
    setLoading(false)
    setLoadError(false)
    setLaunching(false) // Reset launching when system changes

    if (!selectedSystemId) return
    loadData(selectedSystemId)
  }, [selectedSystemId, loadData])

  const sortedGames = [...games]
    .filter(g => formatGameName(g.display_name).toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      if (sort === 'name') return formatGameName(a.display_name).localeCompare(formatGameName(b.display_name))
      if (sort === 'playtime') return (playtimeMap[b.filename]?.total_secs || 0) - (playtimeMap[a.filename]?.total_secs || 0)
      if (sort === 'lastPlayed') {
        const da = playtimeMap[a.filename]?.last_played || ''
        const db = playtimeMap[b.filename]?.last_played || ''
        return db.localeCompare(da)
      }
      return 0
    })

  const selectedGame = sortedGames[selectedGameIdx] ?? sortedGames[0]

  const launchGame = useCallback(async () => {
    if (!selectedSystemId || !selectedGame || launching) return
    setLaunching(true)
    playSound('launch')
    try {
      await api.games.launch(selectedSystemId, selectedGame.path, selectedGame.filename)
      // Block inputs immediately — don't wait for the WebSocket game:started event
      setSession(selectedGame.filename, selectedSystemId)
    } catch (e) {
      console.error(e)
      setLaunching(false)
      setSession(null, null)
    }
  }, [selectedSystemId, selectedGame, launching, setSession])

  // Gamepad — guarded when modal is open or this screen is hidden behind home
  useEffect(() => {
    const blocked = () => {
      return screenRef.current !== 'library' ||
             modalDepthRef.current > 0 ||
             showSearchRef.current ||
             launching ||
             sessionGameKey !== null
    }
    const offs = [
      onGp('gp:dpad-up',  () => { if (blocked()) return; setSelectedGameIdx(Math.max(0, selectedGameIdx - 1)) }),
      onGp('gp:dpad-down',() => { if (blocked()) return; setSelectedGameIdx(Math.min(sortedGames.length - 1, selectedGameIdx + 1)) }),
      onGp('gp:confirm',  () => { if (blocked()) return; launchGame() }),
      onGp('gp:back',     () => { if (screenRef.current !== 'library' || modalDepthRef.current > 0) return; if (showSearchRef.current) { setShowSearch(false); return } goHome() }),
      onGp('gp:y',        () => { if (blocked()) return; setShowSearch(true) }),
      onGp('gp:l1', () => {
        if (blocked()) return
        setSort(s => { const i = SORT_KEYS.indexOf(s); return SORT_KEYS[(i - 1 + SORT_KEYS.length) % SORT_KEYS.length] })
      }),
      onGp('gp:r1', () => {
        if (blocked()) return
        setSort(s => { const i = SORT_KEYS.indexOf(s); return SORT_KEYS[(i + 1) % SORT_KEYS.length] })
      }),
    ]
    return () => offs.forEach(off => off())
  }, [selectedGameIdx, sortedGames.length, launchGame, goHome, setSelectedGameIdx, launching, sessionGameKey])

  // When no system is selected, render nothing (screen is hidden by display:none anyway)
  if (!selectedSystemId) return null

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
    >
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 16, padding: '14px 24px',
        borderBottom: '1px solid rgba(255,255,255,0.06)', flexShrink: 0,
        background: 'rgba(9,9,15,0.5)',
      }}>
        <button onClick={goHome} style={{
          cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
          color: 'rgba(255,255,255,0.45)', fontSize: 13, fontWeight: 500,
          padding: '6px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.1)',
          background: 'transparent',
        }}>‹ Home</button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: color, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {system?.iconPath ? (
              <img src={`/assets/logos/${system.iconPath.split('/').pop()}`} alt="" style={{ width: 20, height: 20, objectFit: 'contain', filter: 'brightness(0) invert(1)' }} />
            ) : (
              <span style={{ color: '#fff', fontSize: 16, fontWeight: 700 }}>{selectedSystemId[0].toUpperCase()}</span>
            )}
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>
              {system?.label || system?.platform || selectedSystemId}
            </div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)' }}>
              {games.length} games
            </div>
          </div>
        </div>

        <div style={{ flex: 1 }} />

        {/* Search */}
        <input
          value={search}
          onChange={e => { setSearch(e.target.value); setSelectedGameIdx(0) }}
          placeholder="Search..."
          style={{
            background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 8, padding: '6px 12px', color: '#fff', fontSize: 13,
            outline: 'none', width: 160,
          }}
        />

        {/* Sort */}
        <div style={{ display: 'flex', gap: 6 }}>
          {([['name', 'A–Z'], ['lastPlayed', 'Recent'], ['playtime', 'Played']] as [SortKey, string][]).map(([v, l]) => (
            <button key={v} onClick={() => setSort(v)} style={{
              padding: '6px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 12, fontWeight: 500,
              background: sort === v ? `rgba(${rgb},0.2)` : 'transparent',
              color: sort === v ? color : 'rgba(255,255,255,0.35)',
              border: sort === v ? `1px solid ${color}50` : '1px solid transparent',
              transition: 'all 0.15s',
            }}>{l}</button>
          ))}
        </div>
      </div>

      {/* Main split */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left: game list */}
        <div style={{ width: 340, flexShrink: 0, overflowY: 'auto', borderRight: '1px solid rgba(255,255,255,0.06)', background: 'rgba(9,9,15,0.3)' }}>
          {loading && (
            <div style={{ padding: 32, textAlign: 'center', color: 'rgba(255,255,255,0.25)', fontSize: 14 }}>
              Loading…
            </div>
          )}
          {!loading && loadError && (
            <div style={{ padding: 32, textAlign: 'center' }}>
              <div style={{ color: 'rgba(255,80,80,0.8)', fontSize: 13, marginBottom: 14 }}>
                Could not reach backend
              </div>
              <button
                onClick={() => selectedSystemId && loadData(selectedSystemId)}
                style={{
                  padding: '8px 18px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.15)',
                  background: 'rgba(255,255,255,0.08)', color: '#fff', fontSize: 13, cursor: 'pointer',
                }}
              >
                Retry
              </button>
            </div>
          )}
          {!loading && !loadError && sortedGames.length === 0 && (
            <div style={{ padding: 32, textAlign: 'center', color: 'rgba(255,255,255,0.25)', fontSize: 14 }}>
              {games.length === 0 ? 'No ROMs found' : 'No results'}
            </div>
          )}
          {sortedGames.map((g, i) => {
            const pt = playtimeMap[g.filename]
            const isSel = i === selectedGameIdx
            return (
              <div
                key={g.filename}
                onClick={() => setSelectedGameIdx(i)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 14, padding: '12px 18px',
                  cursor: 'pointer', borderBottom: '1px solid rgba(255,255,255,0.04)',
                  background: isSel ? `rgba(${rgb},0.1)` : 'transparent',
                  borderLeft: isSel ? `3px solid ${color}` : '3px solid transparent',
                  transition: 'all 0.15s',
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap',
                    overflow: 'hidden', textOverflow: 'ellipsis',
                    color: isSel ? '#fff' : 'rgba(255,255,255,0.85)',
                  }}>{formatGameName(g.display_name)}</div>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', marginTop: 3 }}>
                    {g.ext}
                  </div>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: isSel ? color : 'rgba(255,255,255,0.4)' }}>
                    {pt && pt.total_secs > 0 ? fmtTime(pt.total_secs) : '—'}
                  </div>
                  <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.2)', marginTop: 2 }}>
                    {pt?.last_played ? fmtDate(pt.last_played) : ''}
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Right: game detail */}
        <AnimatePresence mode="wait">
          {selectedGame && (
            <motion.div
              key={selectedGame.filename}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
              style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}
            >
              {/* Ambient background */}
              <div style={{
                position: 'absolute', inset: 0,
                background: `radial-gradient(ellipse 80% 70% at 30% 30%, rgba(${rgb},0.25) 0%, transparent 60%),
                             radial-gradient(ellipse 60% 60% at 75% 70%, rgba(${rgb},0.12) 0%, transparent 55%),
                             #09090f`,
                transition: 'background 0.6s ease',
              }} />
              <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 50%, transparent 20%, rgba(9,9,15,0.5) 100%)', pointerEvents: 'none' }} />

              {/* Cover + info */}
              <div style={{ position: 'relative', zIndex: 2, flex: 1, display: 'flex', flexDirection: 'column', padding: '36px 40px' }}>
                <div style={{ display: 'flex', gap: 32, marginBottom: 32 }}>
                  {/* Cover */}
                  <div style={{
                    width: 180, height: 240, borderRadius: 12, overflow: 'hidden', flexShrink: 0,
                    boxShadow: `0 24px 60px rgba(${rgb},0.4), 0 8px 24px rgba(0,0,0,0.6)`,
                    border: '1px solid rgba(255,255,255,0.1)',
                    background: `rgba(${rgb},0.15)`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <CoverImage filename={selectedGame.filename} systemId={selectedSystemId} color={color} />
                  </div>

                  {/* Info */}
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', letterSpacing: 3, marginBottom: 8 }}>
                      {(system?.label || system?.platform || selectedSystemId).toUpperCase()}
                    </div>
                    <h2 style={{ fontSize: 30, fontWeight: 900, letterSpacing: -0.5, lineHeight: 1.1, marginBottom: 16 }}>
                      {formatGameName(selectedGame.display_name)}
                    </h2>
                    <GameMetaPanel systemId={selectedSystemId} filename={selectedGame.filename} extChip={<Chip label={selectedGame.ext} color={color} />} color={color} />
                    <div style={{ display: 'flex', gap: 24, marginBottom: 28 }}>
                      {[
                        { l: 'Play Time', v: fmtTime(playtimeMap[selectedGame.filename]?.total_secs || 0) },
                        { l: 'Sessions', v: String(playtimeMap[selectedGame.filename]?.session_count || 0) },
                        { l: 'Last Played', v: fmtDate(playtimeMap[selectedGame.filename]?.last_played || null) },
                      ].map(s => (
                        <div key={s.l}>
                          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', letterSpacing: 2, marginBottom: 4 }}>{s.l.toUpperCase()}</div>
                          <div style={{ fontSize: 17, fontWeight: 700, color: '#c4b5fd' }}>{s.v}</div>
                        </div>
                      ))}
                    </div>

                    {/* Play button */}
                    <button
                      onClick={launchGame}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 10,
                        padding: '13px 28px', borderRadius: 12, cursor: 'pointer',
                        background: color, fontSize: 15, fontWeight: 700, color: '#fff',
                        border: 'none', width: 'fit-content',
                        boxShadow: `0 8px 24px rgba(${rgb},0.4)`,
                        transition: 'opacity 0.15s',
                        opacity: launching ? 0.7 : 1,
                      }}
                    >
                      {launching ? '⏳ Launching...' : '▶ Play'}
                    </button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Gamepad hint */}
      <div style={{
        display: 'flex', justifyContent: 'flex-end', padding: '8px 24px',
        borderTop: '1px solid rgba(255,255,255,0.05)', background: 'rgba(9,9,15,0.5)',
      }}>
        <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.15)' }}>
          ↑↓ Navigate · ✕ Play · △ Search · L1/R1 Sort · ○ Back
        </span>
      </div>

      {/* Search virtual keyboard overlay */}
      <AnimatePresence>
        {showSearch && (
          <Overlay onClose={() => setShowSearch(false)}>
            <VirtualKeyboard
              title="Search games"
              onConfirm={val => { setSearch(val); setSelectedGameIdx(0); setShowSearch(false) }}
              onCancel={() => setShowSearch(false)}
            />
          </Overlay>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

function GameMetaPanel({ systemId, filename, extChip, color }: {
  systemId: string; filename: string; extChip: React.ReactNode; color: string
}) {
  const [meta, setMeta] = useState<GameMeta | null>(null)

  useEffect(() => {
    let cancelled = false
    setMeta(null)
    api.metadata.get(systemId, filename)
      .then(m => { if (!cancelled) setMeta(m) })
      .catch(() => {})  // 404 = no metadata (no key / unknown game) — chips row still shows ext
    return () => { cancelled = true }
  }, [systemId, filename])

  return (
    <>
      <div style={{ display: 'flex', gap: 8, marginBottom: meta?.description ? 14 : 24, flexWrap: 'wrap' }}>
        {extChip}
        {meta?.year && <Chip label={meta.year} color={color} />}
        {meta?.genres.slice(0, 3).map(g => <Chip key={g} label={g} color={color} />)}
        {(meta?.players ?? 0) > 1 && <Chip label={`${meta!.players} players`} color={color} />}
      </div>
      {meta?.description && (
        <p style={{
          fontSize: 13.5, lineHeight: 1.55, color: 'rgba(255,255,255,0.55)',
          maxWidth: 640, marginBottom: 24,
          display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>
          {meta.description}
        </p>
      )}
    </>
  )
}

function CoverImage({ filename, systemId, color }: { filename: string; systemId: string; color: string }) {
  const src = `/api/covers/${systemId}/${encodeURIComponent(filename)}`
  const [errored, setErrored] = useState(false)
  const rgb = hexToRgb(color)

  if (errored) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, padding: 16 }}>
        <div style={{ width: 48, height: 48, borderRadius: 12, background: `rgba(${rgb},0.3)`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24 }}>🎮</div>
        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', textAlign: 'center', wordBreak: 'break-all' }}>
          {filename.slice(0, 30)}
        </div>
      </div>
    )
  }

  return (
    <img
      src={src}
      alt={filename}
      onError={() => setErrored(true)}
      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
    />
  )
}
