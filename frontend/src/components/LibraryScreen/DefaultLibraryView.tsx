/**
 * The default library's markup — and nothing else.
 *
 * Selection, sorting, searching and launching all live in LibraryScreen and
 * arrive here as props. This file only says what it looks like, which is the
 * seam a theme replaces: same behaviour, different UI.
 */
import { motion, AnimatePresence } from 'framer-motion'
import { fmtTime, fmtDate, hexToRgb, Chip } from '../ui'
import { formatGameName } from '../../lib/formatGameName'
import { SORT_KEYS, SORT_LABELS, type LibraryViewProps } from './types'

export default function DefaultLibraryView({
  systemId, system, games, totalCount, playtime, selectedIdx, detailGame,
  sort, search, loading, loadError, launching, color,
  onSelect, onSearch, onSort, onLaunch, onBack, onRetry, Cover, Meta,
}: LibraryViewProps) {
  const rgb = hexToRgb(color)

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
        <button onClick={onBack} style={{
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
              <span style={{ color: '#fff', fontSize: 16, fontWeight: 700 }}>{systemId[0].toUpperCase()}</span>
            )}
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>
              {system?.label || system?.platform || systemId}
            </div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)' }}>
              {totalCount} games
            </div>
          </div>
        </div>

        <div style={{ flex: 1 }} />

        {/* Search */}
        <input
          value={search}
          onChange={e => onSearch(e.target.value)}
          placeholder="Search..."
          style={{
            background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 8, padding: '6px 12px', color: '#fff', fontSize: 13,
            outline: 'none', width: 160,
          }}
        />

        {/* Sort */}
        <div style={{ display: 'flex', gap: 6 }}>
          {SORT_KEYS.map(v => (
            <button key={v} onClick={() => onSort(v)} style={{
              padding: '6px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 12, fontWeight: 500,
              background: sort === v ? `rgba(${rgb},0.2)` : 'transparent',
              color: sort === v ? color : 'rgba(255,255,255,0.35)',
              border: sort === v ? `1px solid ${color}50` : '1px solid transparent',
              transition: 'all 0.15s',
            }}>{SORT_LABELS[v]}</button>
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
                onClick={onRetry}
                style={{
                  padding: '8px 18px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.15)',
                  background: 'rgba(255,255,255,0.08)', color: '#fff', fontSize: 13, cursor: 'pointer',
                }}
              >
                Retry
              </button>
            </div>
          )}
          {!loading && !loadError && games.length === 0 && (
            <div style={{ padding: 32, textAlign: 'center', color: 'rgba(255,255,255,0.25)', fontSize: 14 }}>
              {totalCount === 0 ? 'No ROMs found' : 'No results'}
            </div>
          )}
          {games.map((g, i) => {
            const pt = playtime[g.filename]
            const isSel = i === selectedIdx
            return (
              <div
                key={g.filename}
                onClick={() => onSelect(i)}
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
          {detailGame && (
            <motion.div
              key={detailGame.filename}
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
                    <Cover filename={detailGame.filename} systemId={systemId} color={color} />
                  </div>

                  {/* Info */}
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', letterSpacing: 3, marginBottom: 8 }}>
                      {(system?.label || system?.platform || systemId).toUpperCase()}
                    </div>
                    <h2 style={{ fontSize: 30, fontWeight: 900, letterSpacing: -0.5, lineHeight: 1.1, marginBottom: 16 }}>
                      {formatGameName(detailGame.display_name)}
                    </h2>
                    <Meta systemId={systemId} filename={detailGame.filename} extChip={<Chip label={detailGame.ext} color={color} />} color={color} />
                    <div style={{ display: 'flex', gap: 24, marginBottom: 28 }}>
                      {[
                        { l: 'Play Time', v: fmtTime(playtime[detailGame.filename]?.total_secs || 0) },
                        { l: 'Sessions', v: String(playtime[detailGame.filename]?.session_count || 0) },
                        { l: 'Last Played', v: fmtDate(playtime[detailGame.filename]?.last_played || null) },
                      ].map(s => (
                        <div key={s.l}>
                          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', letterSpacing: 2, marginBottom: 4 }}>{s.l.toUpperCase()}</div>
                          <div style={{ fontSize: 17, fontWeight: 700, color: '#c4b5fd' }}>{s.v}</div>
                        </div>
                      ))}
                    </div>

                    {/* Play button */}
                    <button
                      onClick={onLaunch}
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
          ↑↓ Navigate · ✕ Play · △ Search · □ Controller · L1/R1 Sort · ○ Back
        </span>
      </div>
    </motion.div>
  )
}
