/**
 * The default dashboard's markup — and nothing else.
 *
 * Everything that decides *what happens* (paging, focus, launching, the gamepad
 * bindings) stays in HomeScreen. This file only says what it looks like, which
 * is exactly the seam a theme replaces: same behaviour, different UI.
 */
import { motion } from 'framer-motion'
import SystemCard from './SystemCard'
import type { HomeViewProps } from './types'

export default function DefaultHomeView({
  systems, playtime, counts, focusIdx, page, pageCount, cols, rows, perPage,
  totals, onPage, onActivate,
}: HomeViewProps) {
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
            { v: totals.systems, l: 'Systems' },
            { v: totals.games, l: 'Games' },
            { v: `${totals.hours}h`, l: 'Played' },
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
        {page > 0 && (
          <button
            onClick={() => onPage(page - 1)}
            style={{
              position: 'absolute', left: -44, top: '50%', transform: 'translateY(-50%)',
              width: 36, height: 36, borderRadius: '50%', border: '1px solid rgba(255,255,255,0.12)',
              background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.6)',
              fontSize: 22, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
              zIndex: 2, transition: 'all 0.15s',
            }}
          >‹</button>
        )}

        {page < pageCount - 1 && (
          <button
            onClick={() => onPage(page + 1)}
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
            animate={{ x: pageCount > 1 ? `${-(page / pageCount) * 100}%` : 0 }}
            transition={{ type: 'spring', stiffness: 280, damping: 30, clamp: true }}
            style={{ display: 'flex', width: `${Math.max(pageCount, 1) * 100}%` }}
          >
            {Array.from({ length: Math.max(pageCount, 1) }).map((_, pi) => (
              <div key={pi} style={{
                width: `${100 / Math.max(pageCount, 1)}%`, flexShrink: 0,
                display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`,
                gridTemplateRows: `repeat(${rows}, 1fr)`, alignContent: 'start', gap: 12,
              }}>
                {systems.slice(pi * perPage, (pi + 1) * perPage).map((system, i) => (
                  <SystemCard
                    key={system.id}
                    system={system}
                    playtime={playtime[system.id]}
                    gameCount={counts[system.id]}
                    focused={pi === page && i === focusIdx}
                    onClick={() => onActivate(i)}
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
              onClick={() => onPage(i)}
              style={{
                width: i === page ? 20 : 6, height: 6, borderRadius: 3, cursor: 'pointer',
                background: i === page ? '#7c3aed' : 'rgba(255,255,255,0.15)',
                transition: 'all 0.3s',
              }}
            />
          ))}
        </div>
      )}

      {/* Gamepad hint */}
      <div style={{ marginTop: 16, fontSize: 11, color: 'rgba(255,255,255,0.15)', letterSpacing: 1 }}>
        {pageCount > 1 ? '← → Navigate · L1/R1 Page · ✕ Select · □ Controller' : '← → Navigate · ✕ Select · □ Controller'}
      </div>
    </div>
  )
}
