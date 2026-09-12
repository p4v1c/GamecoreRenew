import { useState, useEffect, useRef } from 'react'
import { Overlay, BackHeader } from '../../ui'
import { type CatalogEntry } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { useCatalog } from '../../../lib/catalog'
import { useSubPageGamepad } from './useSubPageGamepad'

/**
 * Add an application to a box that is already running, or take one off it.
 *
 * Steam, Stremio, Twitch, YouTube — the four `kind: 'app'` packs. The consoles
 * are not here any more: they are the Store's Consoles tab, which is a
 * destination reached with △ from the dashboard rather than a page inside the
 * settings. That split is the reason this file is a third of its old length,
 * and the reason it is called `AppsPage` — a page that shows four applications
 * cannot be called the catalogue without lying about what opening it will
 * offer, which is the same fault this repo just removed from a pack manifest.
 *
 * What it still does, it does through `useCatalog` (`lib/catalog.ts`): reading
 * the list, posting the verb, holding the page until `catalog:done`, re-reading
 * after. The Store runs the identical sequence for the consoles from the same
 * hook. There were three hand-written copies of it before and they had already
 * drifted apart in three ways — that file lists them.
 *
 * ── What survived the split, and what did not ──────────────────────────────
 * The old screen carried fixes for four things, and the split settles each:
 *
 *  · **Removing was one button press.** Still is not: ✕ arms, ✕ again removes,
 *    any direction cancels. The rule now lives in `useCatalog`, so the Store
 *    and the rail page get it too — only this page had it before.
 *  · **The focus had to drag the list with it.** Kept. Four rows fit a
 *    television, but `scrollIntoView` costs nothing and the list is data.
 *  · **Twenty systems in one column is a wall**, so they were folded into
 *    accordion groups by maker. Gone with the consoles. Four applications have
 *    no maker worth grouping by — no app pack declares a `family` at all — and
 *    an accordion of one group called "Other" is a fold with nothing behind it.
 *  · **Past a screenful, walking the list stops being navigation**, so △ opened
 *    a virtual keyboard to filter. Gone for the same reason: four rows is not a
 *    screenful, and a search box over four names is furniture.
 */

const ACCENT = 'var(--gc-accent, #7c3aed)'
const mix = (pct: number) => `color-mix(in srgb, ${ACCENT} ${pct}%, transparent)`
const DANGER = '#f87171'

/** What the pill on a row says, and in what colour. */
function rowState(row: CatalogEntry, working: boolean, armed: boolean) {
  if (working) return { label: 'Working…', fg: 'var(--gc-accent-bright, #c4b5fd)', bg: mix(30) }
  if (armed) return { label: 'Confirm?', fg: DANGER, bg: 'rgba(248,113,113,0.22)' }
  if (row.installed) return { label: 'Remove', fg: 'rgba(255,255,255,0.75)', bg: 'rgba(255,255,255,0.07)' }
  return { label: 'Install', fg: 'var(--gc-accent-bright, #c4b5fd)', bg: mix(30) }
}

export function AppsPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const catalog = useCatalog({ kind: 'app' })
  const [focusIdx, setFocusIdx] = useState(0)
  const logEndRef = useRef<HTMLDivElement>(null)
  const focusRowRef = useRef<HTMLDivElement>(null)

  const rows = catalog.rows ?? []

  useSubPageGamepad(onBack, onClose)

  // Read live by the bindings below, which are registered once — the d-pad is
  // edge-triggered and a handler closing over its own render decides twice
  // from the same stale cursor.
  const rowsRef = useRef(rows)
  const focusRef = useRef(focusIdx)
  const catalogRef = useRef(catalog)
  rowsRef.current = rows
  focusRef.current = focusIdx
  catalogRef.current = catalog

  // A list that has just reordered can be shorter than where the cursor was —
  // remove the last row and the index points past the end, which reads as the
  // highlight vanishing rather than as a list that changed.
  useEffect(() => {
    if (rows.length && focusIdx > rows.length - 1) setFocusIdx(rows.length - 1)
  }, [rows.length, focusIdx])

  // Drag the list to the cursor. `block: 'nearest'` scrolls only when the row
  // is actually out of view, so walking the middle does not jerk the container
  // on every step.
  useEffect(() => {
    focusRowRef.current?.scrollIntoView({ block: 'nearest' })
  }, [focusIdx, rows.length])

  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [catalog.log])

  useEffect(() => {
    const move = (d: number) => {
      const n = rowsRef.current.length
      if (!n) return
      catalogRef.current.disarm()      // stepping away is how you say no
      setFocusIdx(i => Math.max(0, Math.min(n - 1, i + d)))
    }
    const offs = [
      onGp('gp:dpad-up', () => move(-1)),
      onGp('gp:dpad-down', () => move(1)),
      onGp('gp:confirm', () => {
        const row = rowsRef.current[focusRef.current]
        if (row) void catalogRef.current.act(row)
      }),
    ]
    return () => offs.forEach(o => o())
  }, [])

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="APPLICATIONS" onBack={onBack} />

      {catalog.loadFailed && (
        <div style={{ color: DANGER, padding: '0 1.5rem 0.5rem' }}>
          The catalogue could not be read.
        </div>
      )}
      {catalog.actionError && (
        <div style={{ color: DANGER, padding: '0 1.5rem 0.5rem' }}>{catalog.actionError}</div>
      )}
      {catalog.rows === null && !catalog.loadFailed && (
        <div style={{ padding: '0 1.5rem', opacity: 0.6 }}>Loading the catalogue…</div>
      )}

      <div style={{ overflowY: 'auto', padding: '0 1.5rem', flex: 1, minHeight: 0 }}>
        {rows.map((row, i) => {
          const focused = i === focusIdx
          const working = catalog.workingId === row.id
          const armed = catalog.armedId === row.id
          const state = rowState(row, working, armed)

          return (
            <div
              key={row.id}
              ref={focused ? focusRowRef : undefined}
              onClick={() => void catalog.act(row)}
              style={{
                display: 'flex', alignItems: 'center', gap: '0.9rem',
                padding: '0.7rem 0.9rem', marginBottom: '0.4rem', borderRadius: 12,
                cursor: catalog.busy ? 'default' : 'pointer',
                // One action at a time box-wide — the backend answers 409 to a
                // second — so the whole list dims rather than letting a player
                // queue up four installs and watch three of them fail.
                opacity: catalog.busy && !working ? 0.35 : 1,
                background: armed ? 'rgba(248,113,113,0.14)'
                  : focused ? mix(18) : 'rgba(255,255,255,0.045)',
                border: `1px solid ${armed ? 'rgba(248,113,113,0.55)'
                  : focused ? mix(55) : 'transparent'}`,
                transition: 'background 120ms ease, border-color 120ms ease',
              }}
            >
              {/* The application's own colour, the same one its tile carries on
                  the grid — the fastest way to find a row you already know. */}
              <div style={{
                width: 4, alignSelf: 'stretch', minHeight: 34, borderRadius: 2,
                background: row.color, flexShrink: 0,
              }} />

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontWeight: 600, display: 'flex', alignItems: 'center',
                  gap: 8, minWidth: 0,
                }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {row.label}
                  </span>
                  {row.origin === 'local' && (
                    <span style={{
                      fontSize: '0.6rem', letterSpacing: '0.08em', padding: '2px 6px',
                      borderRadius: 999, background: mix(28),
                      color: 'var(--gc-accent-bright, #c4b5fd)', flexShrink: 0,
                    }}>LOCAL</span>
                  )}
                </div>

                <div style={{
                  fontSize: '0.78rem', opacity: 0.55, overflow: 'hidden',
                  textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {row.description || row.emulatorName}
                </div>

                {row.restricted.length > 0 && (
                  // A local pack is data only unless the operator opted in.
                  // Saying which blocks were ignored is what stops "why did my
                  // generator not run" being a mystery.
                  <div style={{ fontSize: '0.7rem', color: '#ffb347', marginTop: 2 }}>
                    ignored (local pack): {row.restricted.join(', ')}
                  </div>
                )}
              </div>

              <div style={{
                fontSize: '0.78rem', fontWeight: 700, letterSpacing: '0.04em',
                whiteSpace: 'nowrap', padding: '0.35rem 0.7rem', borderRadius: 999,
                flexShrink: 0, background: state.bg, color: state.fg,
                border: `1px solid ${armed ? 'rgba(248,113,113,0.5)' : 'transparent'}`,
              }}>
                {state.label}
              </div>
            </div>
          )
        })}

        {catalog.rows !== null && rows.length === 0 && !catalog.loadFailed && (
          <div style={{ padding: '1rem 0', opacity: 0.6 }}>
            No application packs are installed on this box.
          </div>
        )}
      </div>

      <div style={{
        padding: '0.5rem 1.5rem 0', fontSize: '0.72rem', opacity: 0.45,
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
      }}>
        {catalog.busy
          ? 'Working — the list is held until this finishes.'
          : catalog.armedId
            ? 'Press ✕ again to remove it · any direction cancels'
            : '✕ install or remove · ○ back'}
      </div>

      {catalog.log.length > 0 && (
        <pre style={{
          margin: '0.5rem 1.5rem 1rem', padding: '0.75rem', maxHeight: '9rem',
          overflowY: 'auto', fontSize: '0.72rem', lineHeight: 1.4,
          background: 'rgba(0,0,0,0.35)', borderRadius: 8, whiteSpace: 'pre-wrap',
        }}>
          {catalog.log.join('\n')}
          <div ref={logEndRef} />
        </pre>
      )}
    </Overlay>
  )
}
