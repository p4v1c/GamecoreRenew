/**
 * The dashboard — one row of big icons, the way a PS4 does it.
 *
 * ── Why a row and not a grid ───────────────────────────────────────────────
 * `HomeScreen` owns the navigation and traverses a COLS × ROWS grid across
 * pages (4 × 2 today). A theme may not touch that. But read its `navigate()`
 * closely and the grid turns out to *already be* a set of horizontal lanes:
 * pressing right at the last column turns the page and lands on `row * COLS` —
 * the same row. So from system 3 you go to system 8, never to 4.
 *
 *     grid, as the host pages it          the same thing, as lanes
 *     page 0      page 1                  lane 0 ▸ 0 1 2 3 8 9 10 11 …
 *     0 1 2 3     8  9 10 11              lane 1 ▸ 4 5 6 7 12 13 14 15 …
 *     4 5 6 7    12 13 14 15
 *
 * Lay one grid row out as a rail and ←→ walks it linearly, right through the
 * page boundary. Nothing is rebound and nothing is reimplemented: the pager
 * the host wrote is exactly what you feel under your thumb.
 *
 * Only the lane you are on is drawn at size. A single unbroken row of every
 * system would be a lie — ←→ cannot reach lane 1 from lane 0, and a row that
 * looks continuous but silently skips half its contents is worse than a
 * visible ↑↓. So the other lane is a strip of small marks: you can see it is
 * there, you can see what is on it, and the foot says which button goes.
 *
 * It reads `cols` and `rows` from props rather than assuming 4 and 2 — a host
 * set to ROWS = 1 gets one row and the strip disappears on its own.
 *
 * ── The icon is the whole tile ─────────────────────────────────────────────
 * No console solid here, unlike the library's spines: a dashboard is read at
 * three metres, and a logo at 200px carries where a box rendered at 40° does
 * not. The name of what you are on is set large above the row, because on a TV
 * a caption under an icon is the first thing to become unreadable.
 */
import { hexToHsl, vars, NEUTRAL } from '../lib/accent.js'
import { played, day } from '../lib/names.js'

/** Tiles either side of the focus. Logos are local and tiny; this is cheap. */
const WINDOW = 8

const initials = (sy) => (sy.platform || sy.label || '??').slice(0, 3).toUpperCase()
const logoOf = (sy) => (sy.iconPath ? String(sy.iconPath).split('/').pop() : null)

export const createHomeView = (sdk, accent) => {
  const { html, useEffect } = sdk.ui

  return ({ systems, playtime, counts, focusIdx, page, pageCount, cols, rows, perPage, totals, onActivate, onPage }) => {
    const screen = sdk.nav.use((s) => s.screen)

    const lanes = Math.max(1, rows || 1)
    const wide = Math.max(1, cols || 1)

    const lane = Math.floor(focusIdx / wide)     // which rail the cursor is on
    const col = focusIdx % wide
    const pos = page * wide + col                // how far along that rail
    const laneLen = Math.max(pageCount, 1) * wide

    /** The system standing at position `q` of lane `r`, or null past the end. */
    const at = (r, q) => {
      const p = Math.floor(q / wide)
      const idx = p * perPage + r * wide + (q % wide)
      return idx < systems.length ? { sy: systems[idx], p, focus: r * wide + (q % wide) } : null
    }

    const here = at(lane, pos)
    const focused = here?.sy
    const tone = hexToHsl(focused?.color) || NEUTRAL

    // The wall takes the colour of the tile in front of you — the same trick
    // the library plays with a jacket. Only while this screen is on show: the
    // library stays mounted behind it and owns the wall when it is.
    useEffect(() => {
      if (screen !== 'home') return
      accent.set(tone)
    }, [screen, focused?.id, focused?.color])

    const isApp = focused && (focused.kind === 'app' || focused.type === 'application')
    const count = focused ? counts[focused.id] ?? 0 : 0
    const pt = focused ? playtime[focused.id] : null

    /** Every cell of one lane, in order. With `paged: false` the host puts the
        whole list on a single page, so this is the entire row. */
    const rowOf = (r) => Array.from({ length: wide }, (_, c) => at(r, page * wide + c))
                              .filter(Boolean)

    /** One tile. `big` is the row you are on; the strip reuses the same cell. */
    const tile = (cell, on, big) => {
      const sy = cell.sy
      const file = logoOf(sy)
      const empty = !(sy.kind === 'app' || sy.type === 'application') && (counts[sy.id] ?? 0) === 0
      return html`
        <div key=${sy.id} class=${big ? 'cz-tile' : 'cz-mini'}
             data-on=${on ? '1' : '0'} data-empty=${empty ? '1' : '0'}
             style=${{ '--sys': sy.color || '#7c3aed' }}
             onClick=${() => { if (cell.p === page) onActivate(cell.focus); else onPage(cell.p) }}>
          <div class="cz-tile-art">
            ${file
              ? html`<img src=${`/assets/logos/${file}`} alt=""
                          onError=${(e) => { e.target.style.display = 'none' }} />`
              : html`<b>${initials(sy)}</b>`}
          </div>
        </div>`
    }

    return html`
      <div class="cz-home cz-ps" data-lanes=${String(lanes)} style=${vars(tone)}>

        <!-- What you are on, set large. The tile carries no label of its own:
             at three metres a caption under an icon is the first casualty. -->
        <div class="cz-ps-head" key=${focused?.id || 'none'}>
          <h2 class="cz-ps-name">${focused?.label || 'No systems yet'}</h2>
          <div class="cz-ps-meta">
            ${focused?.platform ? html`<span class="cz-stamp cz-stamp-std">${focused.platform}</span>` : null}
            <span class="cz-stamp">${isApp ? 'Application' : 'Library'}</span>
            ${isApp ? null : html`<span class="cz-ps-sep">·</span><span>${count || 'no'} games</span>`}
            ${pt?.total_secs ? html`
              <span class="cz-ps-sep">·</span><span>${played(pt.total_secs)}</span>
              <span class="cz-ps-sep">·</span><span>${pt.session_count || 0} sessions</span>
              <span class="cz-ps-sep">·</span><span>${day(pt.last_played)}</span>` : null}
          </div>
        </div>

        <!-- The row travels under a cursor that does not.
             This is only honest without pages, which is why the manifest asks
             for none: while the host paged the list, sliding meant the icons
             moved under your thumb for four presses and then teleported on the
             fifth, and you could never tell which had just happened. With one
             page there is no boundary left to teleport across.
             --n is the count, --i the position: the row centres itself while it
             fits and only starts travelling once it does not. -->
        <div class="cz-ps-stage" style=${{ '--n': String(rowOf(lane).length) }}>
          <div class="cz-ps-row" style=${{ '--i': String(col) }}>
            ${rowOf(lane).map((cell, c) => tile(cell, c === col, true))}
          </div>
        </div>

        <!-- The lane you are not on: small, dim, still legible. It is the only
             honest way to show that ↑↓ leads somewhere. -->
        ${lanes > 1 ? html`
          <div class="cz-ps-strip">
            ${Array.from({ length: lanes }, (_, r) => r === lane ? null : html`
              <div key=${r} class="cz-ps-striprow">
                ${rowOf(r).map((cell) => tile(cell, false, false))}
              </div>`)}
          </div>` : null}

        ${pageCount > 1 ? html`
          <div class="cz-dots">
            ${Array.from({ length: pageCount }, (_, i) => html`
              <span key=${i} class="cz-dot" data-on=${i === page ? '1' : '0'} />`)}
          </div>` : null}

        <!-- The library's foot, deliberately: one count on the left, the
             buttons on the right, so both screens are read the same way. -->
        <div class="cz-foot">
          <div class="cz-count">
            ${totals.games} games across ${totals.systems} systems · ${totals.hours}h played
          </div>
          <div class="cz-keys">
            <kbd>←</kbd><kbd>→</kbd><span>Move</span>
            ${lanes > 1 ? html`<kbd>↑</kbd><kbd>↓</kbd><span>Row</span>` : null}
            ${pageCount > 1 ? html`<kbd>L1</kbd><kbd>R1</kbd><span>Page</span>` : null}
            <kbd class="cz-key-go">✕</kbd><span>${isApp ? 'Launch' : 'Open'}</span>
            <kbd>□</kbd><span>Controller</span>
          </div>
        </div>
      </div>`
  }
}
