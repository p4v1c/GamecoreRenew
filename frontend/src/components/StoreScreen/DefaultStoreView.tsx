/**
 * The default Store's markup — and nothing else.
 *
 * Everything that decides *what happens* (the tabs, paging, focus, the gamepad
 * bindings) stays in StoreScreen. This file only says what it looks like, which
 * is exactly the seam a theme replaces: same behaviour, different UI.
 */
import { useState, useEffect, useRef } from 'react'
import type { CatalogEntry, StoreJob, StoreSearchResult } from '../../api'
import { JOB_STATE_LABELS, isLive } from '../../lib/storeJobs'
import { formatSize } from '../../lib/storeSearch'
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
 * A sentence the tab says instead of drawing a list it does not have.
 *
 * Every empty state on this tab goes through here, because there are six of
 * them and they are six different facts: no console installed, nothing
 * searched for yet, nothing matched, the search failed, nothing has been asked
 * for, and the queue could not be read. Drawing one grid of nothing for all of
 * them would tell a player their query matched nothing when the truth was that
 * the box could not reach the provider — or that they have never queued
 * anything when the truth is that the queue would not answer.
 */
function Nothing({ glyph, title, children }: {
  glyph: string; title: string; children?: React.ReactNode
}) {
  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', gap: 10, textAlign: 'center', padding: '0 48px',
    }}>
      <div style={{ fontSize: 34, opacity: 0.25 }}>{glyph}</div>
      <div style={{ fontSize: 16, fontWeight: 700 }}>{title}</div>
      {children && (
        <div style={{
          fontSize: 13, color: 'rgba(255,255,255,0.4)', maxWidth: 460,
          lineHeight: 1.5,
        }}>{children}</div>
      )}
    </div>
  )
}

/**
 * The banner over invented results.
 *
 * Drawn whenever `gamesLive` is false, and it is the one thing on this tab
 * that must not be quiet about itself: the demo provider makes up rows that
 * look exactly like an indexer's, and a player pressing ✕ on one is asking for
 * a game that does not exist. The honest empty state this tab replaced was
 * better than a convincing lie.
 */
function NotRealNotice({ provider }: { provider: string }) {
  return (
    <div style={{
      flexShrink: 0, marginTop: 12, padding: '7px 12px', borderRadius: 8,
      fontSize: 11.5, lineHeight: 1.45,
      background: 'rgba(250,204,21,0.10)',
      border: '1px solid rgba(250,204,21,0.35)', color: '#fde68a',
    }}>
      <strong>These results are made up.</strong> {provider || 'The demo provider'} invents
      them so this screen can be built and tested — no indexer is configured, nothing
      here is a real download.
    </div>
  )
}

/** One console to search inside. The Games tab's first step. */
function SystemCard({ pack, focused, onClick }: {
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
        }}>{pack.platform || pack.emulatorName}</div>
      </div>
    </div>
  )
}

/**
 * One result — a row, not a card.
 *
 * The format is drawn as its own chip beside the size because those two are
 * what a player is actually choosing between when the same game is listed four
 * times: a `.chd` and a `.cue` of one PlayStation disc are the same game and
 * two different downloads.
 */
function ResultRow({ result, focused, onClick }: {
  result: StoreSearchResult; focused: boolean; onClick: () => void
}) {
  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '9px 14px',
        borderRadius: 10, cursor: 'pointer', minWidth: 0,
        background: focused ? 'rgba(124,58,237,0.16)' : 'rgba(255,255,255,0.035)',
        border: `1px solid ${focused ? 'rgba(124,58,237,0.55)' : 'transparent'}`,
        transition: 'background 120ms ease, border-color 120ms ease',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontWeight: 700, fontSize: 13.5, overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{result.title}</div>
        <div style={{
          fontSize: 11, color: 'rgba(255,255,255,0.38)', marginTop: 2,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{result.filename}</div>
      </div>
      {result.region && (
        <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', flexShrink: 0 }}>
          {result.region}
        </span>
      )}
      {/* Empty when the source does not say — an indexer lists releases, and
          a release named "Zelda - Ocarina of Time (USA)" names no format at
          all. Drawn like `region` above rather than as an empty pill: a badge
          with nothing in it reads as a rendering bug. */}
      {result.format && (
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', flexShrink: 0,
          padding: '2px 7px', borderRadius: 999, color: BRIGHT,
          background: 'rgba(124,58,237,0.20)',
        }}>{result.format.toUpperCase()}</span>
      )}
      <span style={{
        fontSize: 12, color: 'rgba(255,255,255,0.55)', flexShrink: 0,
        minWidth: 62, textAlign: 'right', fontVariantNumeric: 'tabular-nums',
      }}>{formatSize(result.size)}</span>
    </div>
  )
}

/**
 * What one result is, and what asking for it now does — which is queue it.
 *
 * The panel used to end by saying that nothing had been queued, because
 * nothing had: ✕ recorded a choice in component state that died with the
 * screen. It now writes a row to the box's database, and the paragraph at the
 * bottom changed with it — it says what the row will do, which is fail, and
 * why. That is a different sentence from the one it replaced and it has to
 * stay as exact: "queued" and "downloaded" are not the same promise, and this
 * is the screen where a player learns which one they are getting.
 */
function AskedPanel({ result, romsDir, downloadReady, queueing, error }: {
  result: StoreSearchResult; romsDir: string; downloadReady: boolean
  queueing: boolean; error: string
}) {
  const line = (k: string, v: string) => (
    <div style={{ display: 'flex', gap: 12, fontSize: 12.5, minWidth: 0 }}>
      <span style={{ color: 'rgba(255,255,255,0.35)', width: 96, flexShrink: 0 }}>{k}</span>
      <span style={{ color: 'rgba(255,255,255,0.8)', wordBreak: 'break-word' }}>{v}</span>
    </div>
  )
  return (
    <div style={{
      flex: 1, minHeight: 0, marginTop: 18, display: 'flex',
      flexDirection: 'column', gap: 14, overflowY: 'auto',
    }}>
      <div style={{ fontSize: 19, fontWeight: 700 }}>{result.title}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {line('File', result.filename)}
        {line('Format', result.format === 'folder'
          ? 'a folder — this console’s games are directories'
          : result.format
            ? `.${result.format}`
            // Said, not guessed. The panel's job is to tell the player what
            // this is, and "the source did not say" is the true answer — a
            // plausible extension invented here would be the one the ingestion
            // steps key their whole decision on.
            : 'not stated by the source')}
        {line('Size', formatSize(result.size))}
        {result.region && line('Region', result.region)}
        {result.languages.length > 0 && line('Languages', result.languages.join(', '))}
        {/* The concrete reason the console is chosen before anything is
            searched for: with it known, this is known too. */}
        {romsDir && line('Would land in', `${romsDir}/`)}
        {line('Found by', result.provider)}
      </div>
      {error && (
        <div style={{ color: DANGER, fontSize: 12.5, lineHeight: 1.5 }}>{error}</div>
      )}
      {!downloadReady && (
        <div style={{
          marginTop: 'auto', padding: '10px 12px', borderRadius: 8,
          fontSize: 12.5, lineHeight: 1.5,
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.12)',
          color: 'rgba(255,255,255,0.62)',
        }}>
          <strong style={{ color: 'rgba(255,255,255,0.85)' }}>✕ puts this in the
          queue. It will not download.</strong> The queue is real — it is
          written down, it survives a reboot, and you can see what happened to
          it — but there is nothing behind it yet that can fetch a game, so this
          job will end as failed, saying so. Nothing is written into your ROM
          folder either way.
        </div>
      )}
      {queueing && (
        <div style={{ fontSize: 12.5, color: BRIGHT }}>Queueing…</div>
      )}
    </div>
  )
}

/**
 * One job — what was asked for, and what became of it.
 *
 * The state is a chip and the reason is a line under it, because the reason is
 * the half a player can act on: "no acquisition provider is configured on this
 * box" and "the box stopped while this job was running" are two different
 * failures and a row that only said FAILED would make them one.
 */
const JOB_TINT: Record<string, string> = {
  queued: 'rgba(255,255,255,0.45)',
  running: BRIGHT,
  done: '#4ade80',
  failed: DANGER,
  cancelled: 'rgba(255,255,255,0.35)',
}

function JobRow({ job, focused, onClick }: {
  job: StoreJob; focused: boolean; onClick: () => void
}) {
  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '9px 14px',
        borderRadius: 10, minWidth: 0,
        // A finished row has nothing to press: ✕ on it is a no-op, so the
        // pointer must not say otherwise.
        cursor: isLive(job) ? 'pointer' : 'default',
        background: focused ? 'rgba(124,58,237,0.16)' : 'rgba(255,255,255,0.035)',
        border: `1px solid ${focused ? 'rgba(124,58,237,0.55)' : 'transparent'}`,
        transition: 'background 120ms ease, border-color 120ms ease',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontWeight: 700, fontSize: 13.5, overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{job.title}</div>
        <div style={{
          fontSize: 11, color: 'rgba(255,255,255,0.38)', marginTop: 2,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{job.reason || job.filename}</div>
      </div>
      <span style={{
        fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', flexShrink: 0,
        color: JOB_TINT[job.state] ?? 'rgba(255,255,255,0.45)',
      }}>{JOB_STATE_LABELS[job.state] ?? job.state.toUpperCase()}</span>
      <span style={{
        fontSize: 12, color: 'rgba(255,255,255,0.55)', flexShrink: 0,
        minWidth: 62, textAlign: 'right', fontVariantNumeric: 'tabular-nums',
      }}>{formatSize(job.size)}</span>
    </div>
  )
}

/**
 * The queue — everything asked for, and what became of it.
 *
 * Finished rows stay. A download that failed at three in the morning is only
 * ever read about afterwards, and a list that emptied itself on completion
 * would be a list that never explains anything.
 */
function QueueView(p: StoreViewProps) {
  return (
    <>
      <div style={{
        marginTop: 16, flexShrink: 0, display: 'flex', alignItems: 'baseline',
        gap: 10, fontSize: 12.5, color: 'rgba(255,255,255,0.4)',
      }}>
        <span style={{ color: BRIGHT, fontWeight: 700 }}>Queue</span>
        <div style={{ flex: 1 }} />
        {p.gamesJobs.length > 0 && (
          <span>{p.gamesJobsLive} waiting of {p.gamesJobs.length}</span>
        )}
      </div>

      {/* The same rule as the results banner above it: a queue that drew like
          a download in progress would promise bytes nothing here can deliver,
          and the promise would still be on screen after a reboot. */}
      {!p.gamesDownloadReady && (
        <div style={{
          flexShrink: 0, marginTop: 12, padding: '7px 12px', borderRadius: 8,
          fontSize: 11.5, lineHeight: 1.45,
          background: 'rgba(250,204,21,0.10)',
          border: '1px solid rgba(250,204,21,0.35)', color: '#fde68a',
        }}>
          <strong>Nothing here downloads yet.</strong> These jobs are written
          down and they survive a reboot, but there is no provider behind them
          to fetch a game — so each one ends as failed and says why. No file is
          written into any ROM folder.
        </div>
      )}

      {p.gamesQueueError && (
        <div style={{ color: DANGER, fontSize: 12, marginTop: 10, flexShrink: 0 }}>
          {p.gamesQueueError}
        </div>
      )}

      {/* Told apart from an empty queue, which is not an error: one is the box
          failing and the other is a player who has not asked for anything. */}
      {p.gamesJobsError && (
        <Nothing glyph="⚠" title={p.gamesJobsError}>
          Press ○ to go back and try again.
        </Nothing>
      )}

      {!p.gamesJobsError && p.gamesJobs.length === 0 && (
        <Nothing glyph="◌" title="Nothing asked for yet">
          Pick a console, search it, and press ✕ on a result to put it here.
        </Nothing>
      )}

      {!p.gamesJobsError && p.gamesJobsPage.length > 0 && (
        <div style={{
          flex: 1, minHeight: 0, marginTop: 12,
          display: 'flex', flexDirection: 'column', gap: 7,
          alignContent: 'start',
        }}>
          {p.gamesJobsPage.map((job, i) => (
            <JobRow
              key={job.id}
              job={job}
              focused={i === p.focusIdx}
              onClick={() => { p.onFocus(i); p.onGamesCancelJob(job) }}
            />
          ))}
        </div>
      )}
    </>
  )
}

/**
 * The Games tab: pick a console, then search inside it.
 *
 * Two steps and in that order, which is a decision the host makes and this
 * view only draws — the ingestion class of a download is a property of the
 * pair (system, incoming format) and the target directory belongs to the
 * system, so a result found without a console attached could be neither placed
 * nor classified. See docs/architecture/14-store-ingestion-matrix.md §0.
 */
function GamesTab(p: StoreViewProps) {
  // The queue first, and before the no-console check below it: what has
  // already been asked for is still worth reading on a box whose last console
  // has just been removed, and a player who pressed △ must not land on a
  // sentence about installing something.
  if (p.gamesPhase === 'queue') return <QueueView {...p} />

  if (p.gamesSystems.length === 0) {
    return (
      <Nothing glyph="◌" title="No console to search yet">
        A game is searched for inside a console, because where it has to land
        and what has to be done to it both depend on which machine it is for.
        Install one from the Consoles tab and it appears here.
      </Nothing>
    )
  }

  if (p.gamesPhase === 'systems') {
    return (
      <>
        <div style={{
          marginTop: 16, flexShrink: 0, display: 'flex', alignItems: 'baseline',
          gap: 10, fontSize: 12.5, color: 'rgba(255,255,255,0.4)',
        }}>
          <span>Which console are you looking for a game for?</span>
          <div style={{ flex: 1 }} />
          {/* The way in to the queue for a pointer, and the count that makes
              △ worth pressing. Drawn whenever anything has ever been asked
              for, not only while something is live: the finished rows are the
              half a player comes back to read. */}
          {p.gamesJobs.length > 0 && (
            <span onClick={p.onGamesQueueOpen} style={{ cursor: 'pointer', color: BRIGHT }}>
              △ queue ({p.gamesJobsLive || p.gamesJobs.length})
            </span>
          )}
        </div>
        <div style={{
          flex: 1, minHeight: 0, marginTop: 12,
          display: 'grid', gap: 12, alignContent: 'start',
          gridTemplateColumns: `repeat(${p.cols}, minmax(0, 1fr))`,
          gridTemplateRows: `repeat(${p.rows}, minmax(0, auto))`,
        }}>
          {p.gamesSystemsPage.map((pack, i) => (
            <SystemCard
              key={pack.id}
              pack={pack}
              focused={i === p.focusIdx}
              onClick={() => { p.onFocus(i); p.onGamesSystem(pack) }}
            />
          ))}
        </div>
      </>
    )
  }

  if (p.gamesAsked) {
    return (
      <AskedPanel
        result={p.gamesAsked}
        romsDir={p.gamesRomsDir}
        downloadReady={p.gamesDownloadReady}
        queueing={p.gamesQueueing}
        error={p.gamesQueueError}
      />
    )
  }

  return (
    <>
      <div style={{
        marginTop: 16, flexShrink: 0, display: 'flex', alignItems: 'baseline',
        gap: 10, fontSize: 12.5, color: 'rgba(255,255,255,0.4)',
      }}>
        <span style={{ color: BRIGHT, fontWeight: 700 }}>{p.gamesSystem?.label}</span>
        {p.gamesQuery && <span>“{p.gamesQuery}”</span>}
        <div style={{ flex: 1 }} />
        {p.gamesAnswered && !p.gamesLoading && (
          <span>{p.gamesResults.length} result{p.gamesResults.length === 1 ? '' : 's'}</span>
        )}
      </div>

      {!p.gamesLive && p.gamesAnswered && <NotRealNotice provider={p.gamesProvider} />}

      {p.gamesLoading && (
        <Nothing glyph="◌" title="Searching…" />
      )}

      {/* Told apart from "nothing matched" on purpose: one is the box failing
          and the other is the query. Blaming the query for a provider that did
          not answer sends the player off to retype a title that was fine. */}
      {!p.gamesLoading && p.gamesError && (
        <Nothing glyph="⚠" title={p.gamesError}>
          Nothing was searched. Press △ to try again.
        </Nothing>
      )}

      {!p.gamesLoading && !p.gamesError && p.gamesAnswered && p.gamesResults.length === 0 && (
        <Nothing glyph="◌" title="Nothing matched">
          No result for “{p.gamesQuery}” on {p.gamesSystem?.label}. Press △ to
          search for something else.
        </Nothing>
      )}

      {!p.gamesLoading && !p.gamesError && !p.gamesAnswered && (
        <Nothing glyph="◌" title="Nothing searched for yet">
          Press △ to type what you are looking for.
        </Nothing>
      )}

      {!p.gamesLoading && !p.gamesError && p.gamesResultsPage.length > 0 && (
        <div style={{
          flex: 1, minHeight: 0, marginTop: 12,
          display: 'flex', flexDirection: 'column', gap: 7,
          alignContent: 'start',
        }}>
          {p.gamesResultsPage.map((result, i) => (
            <ResultRow
              key={result.id}
              result={result}
              focused={i === p.focusIdx}
              onClick={() => { p.onFocus(i); p.onGamesAsk(result) }}
            />
          ))}
        </div>
      )}
    </>
  )
}

export default function DefaultStoreView(p: StoreViewProps) {
  const {
    tab, tabs, tabLabels, pageItems, focusIdx, page, pageCount, cols, rows,
    consoles, installedCount, loading, loadError, onTab, onFocus, onPage, onBack,
    onRetry, workingId, busy, armedId, log, actionError, onAct,
  } = p
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

      {tab === 'games' ? <GamesTab {...p} /> : (
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

        </>
      )}

      {/* Outside the tab branch: the Games tab pages too — up to three pages of
          consoles and six of results — and a list that turns pages with no dot
          to say so reads as a list that jumped. `pageCount` is already the
          current list's, so one pager serves all three. The asked-about panel
          is the exception: it is one thing, not a page of them. */}
      {pageCount > 1 && !(tab === 'games' && p.gamesAsked) && (
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
        {/* The Games tab's hint follows its step, because the same two buttons
            mean three different things across them and a bar that said one of
            them everywhere would be wrong twice. */}
        {tab === 'games' && (p.gamesSystems.length > 0 || p.gamesPhase === 'queue') && (
          <span>
            {p.gamesPhase === 'queue' ? '✕ stop a waiting job · ○ back'
              : p.gamesPhase === 'systems' ? '✕ search this console · △ the queue'
                : p.gamesAsked ? '✕ put it in the queue · ○ back to the results'
                  : '✕ what is this · △ search again'}
          </span>
        )}
        {/* ○ steps back through the Games tab before it leaves the screen, so
            the pointer affordance has to do the same or the two disagree. */}
        {tab === 'games' && (p.gamesPhase === 'queue' || p.gamesAsked || p.gamesSystem)
          ? <span onClick={p.onGamesBack} style={{ cursor: 'pointer' }}>○ Back</span>
          : <span onClick={onBack} style={{ cursor: 'pointer' }}>○ Back</span>}
        <div style={{ flex: 1 }} />
        {tab === 'consoles' && busy && (
          <span>Working — the grid is held until this finishes</span>
        )}
      </div>
    </div>
  )
}
