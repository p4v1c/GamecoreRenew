/**
 * The default Store's markup — and nothing else.
 *
 * Everything that decides *what happens* (the tabs, paging, focus, the gamepad
 * bindings) stays in StoreScreen. This file only says what it looks like, which
 * is exactly the seam a theme replaces: same behaviour, different UI.
 */
import { useState, useEffect } from 'react'
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

function ConsoleCard({ pack, focused, onClick }: {
  pack: CatalogEntry; focused: boolean; onClick: () => void
}) {
  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
        borderRadius: 14, cursor: 'pointer', minWidth: 0,
        background: focused ? 'rgba(124,58,237,0.16)' : 'rgba(255,255,255,0.045)',
        border: `1px solid ${focused ? 'rgba(124,58,237,0.55)' : 'transparent'}`,
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
        {/* A state, not a button. Installing is still driven from
            Settings → Emulators & apps, and a card that offered to do it here
            and did nothing would be the worst of the three options. */}
        <div style={{
          marginTop: 6, fontSize: 10, letterSpacing: '0.08em', fontWeight: 700,
          color: pack.installed ? '#4ade80' : 'rgba(255,255,255,0.3)',
        }}>
          {pack.installed ? '● ON THIS BOX' : '○ NOT INSTALLED'}
        </div>
      </div>
    </div>
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
  onRetry,
}: StoreViewProps) {
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
              from the settings over this screen — keeps the grid up rather
              than dropping the player's cursor into a "loading" line and
              putting it back a moment later. */}
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
                  onClick={() => onFocus(i)}
                />
              ))}
            </div>
          )}

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
        <span onClick={onBack} style={{ cursor: 'pointer' }}>○ Back</span>
        <div style={{ flex: 1 }} />
        {tab === 'consoles' && (
          <span>Installing is still in Settings → Emulators &amp; apps</span>
        )}
      </div>
    </div>
  )
}
