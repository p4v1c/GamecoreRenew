/**
 * The default Store's markup — and nothing else.
 *
 * Everything that decides *what happens* (the tabs, paging, focus, the gamepad
 * bindings) stays in StoreScreen. This file only says what it looks like, which
 * is exactly the seam a theme replaces: same behaviour, different UI.
 */
import { useState, useEffect, useRef } from 'react'
import type { CatalogEntry } from '../../api'
import type { StoreViewProps } from './types'

const ACCENT = '#7c3aed'
const BRIGHT = '#c4b5fd'

/**
 * The pack's own logo, with its colour as the fallback it has always been.
 *
 * A component rather than an `<img>` because the failure is asynchronous: the
 * URL looks fine until the image does not arrive, and a broken-image glyph on
 * a television is worse than the swatch. The tile behind it is a constant
 * near-white: these logos are somebody else's artwork at somebody else's
 * contrast — several are dark line art, several are near-white — and a light
 * chip is the only ground that works for all of them at once.
 */
function PackMark({ pack }: { pack: CatalogEntry }) {
  const [failed, setFailed] = useState(false)
  // Reset when the card is reused for another pack: `failed` is about one
  // image, and React keeps this component mounted across a re-key.
  useEffect(() => { setFailed(false) }, [pack.logo])

  const box = {
    width: 44, height: 44, borderRadius: 10, flexShrink: 0,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  } as const

  if (!pack.logo || failed) {
    return <div style={{ ...box, background: pack.color || '#8B8992' }} />
  }
  return (
    <div style={{ ...box, background: 'rgba(255,255,255,0.92)', padding: 6 }}>
      <img
        src={`/${pack.logo}`} alt="" loading="lazy"
        onError={() => setFailed(true)}
        style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
      />
    </div>
  )
}

const DANGER = '#f87171'

/**
 * What the card says it will do, and what it looks like saying it.
 *
 * Four states rather than two, because the two that were added are the ones a
 * player is most likely to misread: `armed` has to look unlike anything else on
 * the screen or the first ✕ reads as a press that did nothing, and `working`
 * has to hold its own row rather than flicker back to "Install" between the
 * post and the first line of output.
 */
function cardState(pack: CatalogEntry, working: boolean, armed: boolean) {
  if (working) return { label: 'WORKING…', tint: BRIGHT, fill: 'rgba(124,58,237,0.22)' }
  if (armed) return { label: 'REMOVE — ✕ AGAIN', tint: DANGER, fill: 'rgba(248,113,113,0.22)' }
  if (pack.installed) return { label: '● ON THIS BOX', tint: '#4ade80', fill: 'transparent' }
  return { label: '○ NOT INSTALLED', tint: 'rgba(255,255,255,0.3)', fill: 'transparent' }
}

function ConsoleCard({ pack, focused, working, armed, held, onClick }: {
  pack: CatalogEntry; focused: boolean; working: boolean; armed: boolean
  held: boolean; onClick: () => void
}) {
  const state = cardState(pack, working, armed)
  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
        borderRadius: 14, cursor: held ? 'default' : 'pointer', minWidth: 0,
        // Held, and saying so: one action runs at a time box-wide, so every
        // other card dims rather than offering a press that would 409.
        opacity: held && !working ? 0.35 : 1,
        background: armed ? 'rgba(248,113,113,0.14)'
          : focused ? 'rgba(124,58,237,0.16)' : 'rgba(255,255,255,0.045)',
        border: `1px solid ${armed ? 'rgba(248,113,113,0.55)'
          : focused ? 'rgba(124,58,237,0.55)' : 'transparent'}`,
        transition: 'background 120ms ease, border-color 120ms ease',
      }}
    >
      <PackMark pack={pack} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontWeight: 700, fontSize: 14, overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{pack.label}</div>
        <div style={{
          fontSize: 11.5, color: 'rgba(255,255,255,0.45)', marginTop: 2,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{pack.emulatorName}</div>
        <div style={{
          marginTop: 6, fontSize: 10, letterSpacing: '0.08em', fontWeight: 700,
          color: state.tint, background: state.fill,
          padding: state.fill === 'transparent' ? 0 : '2px 6px',
          borderRadius: 999, width: 'fit-content', maxWidth: '100%',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {state.label}
        </div>
      </div>
    </div>
  )
}

/**
 * `gamecore-emu`'s output, while there is any.
 *
 * A Flatpak on a slow line is minutes of nothing, and a card that only said
 * "Working…" for four of them is indistinguishable from one that has hung. The
 * pane is the same answer the settings page has always given, and it is why
 * `CATALOG_FAILED` does not have to name a place to look.
 */
function RunLog({ lines }: { lines: string[] }) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [lines])
  return (
    <pre style={{
      margin: '10px 0 0', padding: '8px 10px', maxHeight: '7rem', flexShrink: 0,
      overflowY: 'auto', fontSize: 11, lineHeight: 1.45, whiteSpace: 'pre-wrap',
      background: 'rgba(0,0,0,0.35)', borderRadius: 8,
    }}>
      {lines.join('\n')}
      <div ref={endRef} />
    </pre>
  )
}

/**
 * The Games tab, which has nothing to list and says so.
 *
 * Not an empty grid and not a placeholder list: either would read as "you own
 * no games", which is a different sentence and a false one. The tab exists now
 * because the Store's shape is two tabs and a theme has to be able to dress
 * both of them; what fills it — searching, downloading, and the six ingestion
 * classes a download has to become (docs/architecture/14-store-ingestion-matrix.md
 * §5) — arrives in its own steps.
 */
function GamesTab() {
  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', gap: 10, textAlign: 'center', padding: '0 48px',
    }}>
      <div style={{ fontSize: 34, opacity: 0.25 }}>◌</div>
      <div style={{ fontSize: 16, fontWeight: 700 }}>Downloading games is not here yet</div>
      <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.4)', maxWidth: 460, lineHeight: 1.5 }}>
        This tab is the place it will land. Nothing searches, downloads or
        installs from it today — until it does, put your ROMs on the box the way
        you already do and they appear in your library.
      </div>
    </div>
  )
}

export default function DefaultStoreView({
  tab, tabs, tabLabels, pageItems, focusIdx, page, pageCount, cols, rows,
  consoles, installedCount, loading, loadError, onTab, onFocus, onPage, onBack,
  onRetry, workingId, busy, armedId, log, actionError, onAct,
}: StoreViewProps) {
  const focusedPack = pageItems[focusIdx]
  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      padding: '20px 48px 14px', overflow: 'hidden',
    }}>
      {/* Tabs. L1/R1 walk them; the pills are the pointer's way in. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
        <span style={{
          fontSize: 12, color: 'rgba(255,255,255,0.25)', letterSpacing: 3,
          marginRight: 6,
        }}>STORE</span>
        {tabs.map(id => (
          <button
            key={id}
            onClick={() => onTab(id)}
            style={{
              padding: '7px 18px', borderRadius: 999, cursor: 'pointer',
              fontSize: 13, fontWeight: 700, letterSpacing: '0.03em',
              background: id === tab ? 'rgba(124,58,237,0.22)' : 'transparent',
              border: `1px solid ${id === tab ? 'rgba(124,58,237,0.6)' : 'rgba(255,255,255,0.1)'}`,
              color: id === tab ? BRIGHT : 'rgba(255,255,255,0.45)',
              transition: 'all 0.15s',
            }}
          >{tabLabels[id]}</button>
        ))}
        <div style={{ flex: 1 }} />
        {tab === 'consoles' && !loadError && consoles.length > 0 && (
          <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)' }}>
            {installedCount} of {consoles.length} installed
          </span>
        )}
      </div>

      {tab === 'games' ? <GamesTab /> : (
        <>
          {/* The placeholder only while there is genuinely nothing to draw. A
              reload — the catalogue answering again after a pack was installed
              — keeps the grid up rather than dropping the player's cursor into
              a "loading" line and putting it back a moment later. That reload
              follows every install, so it is the common case, not the rare
              one. */}
          {loading && pageItems.length === 0 && !loadError && (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.5 }}>
              Loading the catalogue…
            </div>
          )}

          {loadError && (
            <div style={{
              flex: 1, display: 'flex', flexDirection: 'column', gap: 12,
              alignItems: 'center', justifyContent: 'center',
            }}>
              <div style={{ color: '#f87171' }}>The catalogue could not be read.</div>
              <button
                onClick={onRetry}
                style={{
                  padding: '8px 20px', borderRadius: 999, cursor: 'pointer',
                  background: 'rgba(124,58,237,0.22)', color: BRIGHT,
                  border: `1px solid ${ACCENT}80`, fontSize: 13, fontWeight: 700,
                }}
              >Try again</button>
            </div>
          )}

          {!loadError && (pageItems.length > 0 || !loading) && (
            <div style={{
              flex: 1, minHeight: 0, marginTop: 18,
              display: 'grid', gap: 12, alignContent: 'start',
              gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
              gridTemplateRows: `repeat(${rows}, minmax(0, auto))`,
            }}>
              {pageItems.map((pack, i) => (
                <ConsoleCard
                  key={pack.id}
                  pack={pack}
                  focused={i === focusIdx}
                  working={workingId === pack.id}
                  armed={armedId === pack.id}
                  held={busy}
                  // A click both moves the cursor and acts, the way the
                  // settings list has always behaved under a pointer: the
                  // second click on an installed pack is the confirmation.
                  onClick={() => { onFocus(i); onAct(pack) }}
                />
              ))}
            </div>
          )}

          {actionError && (
            <div style={{ color: DANGER, fontSize: 12, marginTop: 10, flexShrink: 0 }}>
              {actionError}
            </div>
          )}

          {log.length > 0 && <RunLog lines={log} />}

          {!loading && !loadError && consoles.length === 0 && (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.6 }}>
              The catalogue is empty — no packs are installed on this box.
            </div>
          )}

          {pageCount > 1 && (
            <div style={{ display: 'flex', gap: 6, justifyContent: 'center', marginTop: 14 }}>
              {Array.from({ length: pageCount }).map((_, i) => (
                <div
                  key={i}
                  onClick={() => onPage(i)}
                  style={{
                    width: i === page ? 20 : 6, height: 6, borderRadius: 3, cursor: 'pointer',
                    background: i === page ? ACCENT : 'rgba(255,255,255,0.15)',
                    transition: 'all 0.3s',
                  }}
                />
              ))}
            </div>
          )}
        </>
      )}

      <div style={{
        marginTop: 12, flexShrink: 0, display: 'flex', alignItems: 'center',
        gap: 16, fontSize: 11, color: 'rgba(255,255,255,0.2)', letterSpacing: 1,
      }}>
        <span>L1/R1 Tab</span>
        {tab === 'consoles' && <span>← → Navigate</span>}
        {tab === 'consoles' && !busy && (
          <span>
            {armedId ? '✕ remove it · any direction cancels'
              : focusedPack?.installed ? '✕ remove · △ reconfigure'
                : '✕ install'}
          </span>
        )}
        <span onClick={onBack} style={{ cursor: 'pointer' }}>○ Back</span>
        <div style={{ flex: 1 }} />
        {tab === 'consoles' && busy && (
          <span>Working — the grid is held until this finishes</span>
        )}
      </div>
    </div>
  )
}
