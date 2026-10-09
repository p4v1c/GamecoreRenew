/**
 * The dashboard, set like a studio product shot.
 *
 * Top left, the copy: maker, year and kind in the console's colour, its name
 * set large, one sentence, what you have done with it (games, time, last
 * played), the two things ✕ and △ do, and the last games you played on it.
 * On the right, the console itself, photographed. Along the bottom the paper
 * fades to white like a photographer's sweep, and every console stands on it
 * as an object; then, past a thin rule, the apps as white icon tiles.
 *
 * The wall behind is still Shelf's paper. A full-screen colour wash per console
 * was tried in the mockups and turned down: it read as generated, and it
 * repainted the room on every step, which is the same reason the wall stopped
 * taking the jacket's colour (README.md, "Two accents").
 *
 * Behaviour is the host's, as before. HomeScreen owns ←/→ (one row: the
 * manifest asks for `rows: 1, paged: false`), ✕ (open the library, or launch /
 * resume an app) and □. The theme binds one button the host leaves free on
 * this screen, △, for the secondary action the copy block prints:
 *
 *   console with a last-played game   △ starts that game (sdk.defaults.launchGame)
 *   app running in the background      △ closes it, after a second press
 *
 * ↑/↓ do nothing here, as before: this screen has a single row and no other
 * zone to move to, and the recent covers are a picture of history, not a menu.
 *
 * Every figure is the box's own. A console nobody described has no eyebrow and
 * no sentence (lib/consoles.js), one nobody played has no time and no recent
 * strip, and an app nobody opened has no stats at all.
 */
import { describe, isApp, shortName } from '../lib/consoles.js'
import { createHomeData, duration, when } from '../lib/home-data.js'
import { onPaper } from '../lib/accent.js'
import { title } from '../lib/names.js'
import { jacket } from '../lib/dossier.js'
import { trimmed, trimmedNow } from '../lib/trim.js'
import { CLOSE_MS } from './ceremony.js'

/** A second △ within this long closes the app; after it, the first is forgotten. */
const CONFIRM_MS = 3000

const logoOf = (sy) => (sy?.iconPath
  ? `/assets/logos/${encodeURIComponent(String(sy.iconPath).replace(/\\/g, '/').split('/').pop())}`
  : null)

/** The console photo the pack ships (docs/themes/README.md §7.0), else its logo. */
const photoOf = (sy) => sy?.art?.console || logoOf(sy)

export const createHomeView = (sdk) => {
  const { html, useState, useEffect, useRef } = sdk.ui
  const PadKey = sdk.ui.PadKey || (({ k }) => html`<kbd>${k}</kbd>`)
  const { usePlaytimeRows, useRecent } = createHomeData(sdk)

  /** The pad may act here only while nothing the core owns is up. */
  const free = () => {
    const s = sdk.nav.get()
    return s.screen === 'home' && !s.modalDepth && !s.sessionGameKey && !s.transition
      && !s.powerPending && (s.standby == null || s.standby === 'off')
  }

  /** An app's logo, cropped to its ink so every tile holds a mark of one size. */
  const AppMark = ({ src }) => {
    const [url, setUrl] = useState(() => trimmedNow(src))
    useEffect(() => {
      let live = true
      setUrl(trimmedNow(src))
      trimmed(src).then((u) => { if (live) setUrl(u) })
      return () => { live = false }
    }, [src])
    // Nothing until the crop is known: drawing the padded file first and then
    // the cropped one is a visible jump in size.
    return url ? html`<img src=${url} alt="" draggable="false" />` : null
  }

  /** One object on the sweep: a console photo, or an app's white tile. */
  const Cell = ({ sy, on, onClick }) => {
    const app = isApp(sy)
    const photo = photoOf(sy)
    return html`
      <div class="cz-st-cell" data-on=${on ? '1' : '0'} data-app=${app ? '1' : '0'}
           onClick=${onClick}>
        <div class="cz-st-obj">
          ${app
            ? html`<span class="cz-st-ic"><${AppMark} src=${logoOf(sy)} /></span>`
            : photo
              ? html`<img src=${photo} alt="" draggable="false" decoding="async"
                          onError=${(e) => { e.target.style.visibility = 'hidden' }} />`
              : html`<b class="cz-st-initials">${shortName(sy).slice(0, 4)}</b>`}
        </div>
        <span class="cz-st-name">${shortName(sy)}</span>
      </div>`
  }

  return ({ systems, playtime, counts, focusIdx, page, perPage, totals, onActivate, onPage }) => {
    const idx = page * perPage + focusIdx
    const focused = systems[idx] || null
    const app = isApp(focused)
    const info = describe(focused)

    const rows = usePlaytimeRows()
    const recent = useRecent(focused, rows, app)
    const { background = [] } = sdk.session?.use?.() || {}
    // An app launches with game_key === system_id (docs/themes §5f), so this
    // is the app itself sitting in the background, not a game on its console.
    const heldApp = app ? background.find((s) => s.kind === 'app' && s.systemId === focused.id) || null : null

    const pt = focused ? playtime[focused.id] : null
    const count = focused ? counts[focused.id] : undefined
    const last = recent[0] || null

    // The console's own colour, made legible: one for text, one for lines.
    const ink = onPaper(focused?.color, 4.6) || 'var(--ink)'
    const line = onPaper(focused?.color, 3) || 'var(--ink)'

    // ── △ ──────────────────────────────────────────────────────────────
    const [arming, setArming] = useState(null)        // app id waiting for a 2nd △
    useEffect(() => { setArming(null) }, [focused?.id])
    useEffect(() => {
      if (!arming) return
      const t = setTimeout(() => setArming(null), CONFIRM_MS)
      return () => clearTimeout(t)
    }, [arming])

    const live = useRef({})
    live.current = { focused, app, last, heldApp, arming }
    useEffect(() => sdk.input.onGp('gp:y', () => {
      if (!free()) return
      const { focused: sy, app: isAnApp, last: game, heldApp: h, arming: armed } = live.current
      if (!sy) return
      if (isAnApp) {
        if (!h) return
        if (armed !== sy.id) { setArming(sy.id); return }
        setArming(null)
        sdk.session.close(h.session).catch(() => {})
        return
      }
      if (!game?.path) return
      sdk.defaults.launchGame?.({ systemId: sy.id, path: game.path, gameKey: game.filename }, CLOSE_MS)
        ?.catch?.(() => {})
    }), [])

    // ── the row keeps the focus in view ──────────────────────────────────
    // Measured from the DOM rather than computed from constants, so the row
    // stays right whatever the sizes in home.css become. Written straight to
    // the element: a re-render per step would be a frame late.
    const firstApp = systems.findIndex(isApp)
    const wrapRef = useRef(null)
    const rowRef = useRef(null)
    useEffect(() => {
      const wrap = wrapRef.current, row = rowRef.current
      if (!wrap || !row) return
      const cell = row.children[idx + (firstApp >= 0 && idx >= firstApp ? 1 : 0)]
      if (!cell) return
      const edge = parseFloat(getComputedStyle(wrap).getPropertyValue('--st-edge')) || 0
      const W = wrap.clientWidth, R = row.scrollWidth
      const centre = cell.offsetLeft + cell.offsetWidth / 2
      // Centred while it fits; once it does not, follow the focus but never
      // pull an end of the row in past the edge margin.
      const x = R <= W - 2 * edge ? (W - R) / 2
        : Math.max(W - edge - R, Math.min(edge, W / 2 - centre))
      row.style.transform = `translate3d(${Math.round(x)}px, 0, 0)`
    }, [idx, systems.length])

    // ── copy ───────────────────────────────────────────────────────────
    const stats = []
    if (!app && count != null) stats.push([String(count), count === 1 ? 'game' : 'games'])
    if (duration(pt?.total_secs)) stats.push([duration(pt.total_secs), 'played'])
    if (when(pt?.last_played)) stats.push([when(pt.last_played), app ? 'last opened' : 'last played'])

    const name = focused ? info.name : 'No systems yet'
    const lastName = last ? title(last.display_name || last.filename) : null

    return html`
      <div class="cz-home cz-studio" data-app=${app ? '1' : '0'}
           data-ledge=${background.length ? '1' : '0'}
           style=${{ '--k': line, '--k-ink': ink }}>

        <div class="cz-st-sweep" aria-hidden="true" />

        ${focused ? html`
          <div class="cz-st-hero" key=${`hero:${focused.id}`} aria-hidden="true">
            ${app
              ? html`<div class="cz-st-bigic"><${AppMark} src=${logoOf(focused)} /></div>`
              : photoOf(focused)
                ? html`<img src=${photoOf(focused)} alt="" draggable="false" />`
                : null}
          </div>` : null}

        <div class="cz-st-left">
        <div class="cz-st-copy" key=${`copy:${focused?.id || 'none'}`}>
          ${info.eyebrow.length ? html`<div class="cz-st-eyebrow">${info.eyebrow.join(' · ')}</div>` : null}
          <h1 class="cz-st-name-big">${name}</h1>
          ${info.story ? html`<p class="cz-st-desc">${info.story}</p>` : null}

          ${stats.length || heldApp ? html`
            <div class="cz-st-stats">
              ${stats.map(([v, k]) => html`<div class="cz-st-stat" key=${k}><b>${v}</b>${k}</div>`)}
              ${heldApp ? html`<div class="cz-st-stat cz-st-run"><b>Open</b>in the background</div>` : null}
            </div>` : null}

          ${focused ? html`
            <div class="cz-st-btns">
              <button class="cz-st-btn cz-st-btn-go" onClick=${() => onActivate(focusIdx)}>
                <${PadKey} k="✕" />
                ${app ? `${heldApp ? 'Resume' : 'Open'} ${focused.label || focused.id}` : 'Open library'}
              </button>
              ${heldApp ? html`
                <button class="cz-st-btn" data-armed=${arming === focused.id ? '1' : '0'}
                        onClick=${() => (arming === focused.id
                          ? (setArming(null), sdk.session.close(heldApp.session).catch(() => {}))
                          : setArming(focused.id))}>
                  <${PadKey} k="△" />
                  ${arming === focused.id ? 'Press again to close' : `Close ${focused.label || focused.id}`}
                </button>` : null}
              ${!app && lastName ? html`
                <button class="cz-st-btn"
                        onClick=${() => sdk.defaults.launchGame?.({ systemId: focused.id, path: last.path, gameKey: last.filename }, CLOSE_MS)?.catch?.(() => {})}>
                  <${PadKey} k="△" />
                  <span class="cz-st-btn-txt">Resume ${lastName}</span>
                </button>` : null}
            </div>` : null}
        </div>

        ${recent.length ? html`
          <div class="cz-st-recent" key=${`recent:${focused.id}`}>
            <h3>Recently played</h3>
            <div class="cz-st-covers">
              ${recent.map((g) => html`
                <div class="cz-st-cover" key=${g.filename}>
                  <img src=${jacket(focused.id, g.filename)} alt="" draggable="false"
                       onError=${(e) => { e.target.style.visibility = 'hidden' }} />
                  <b>${title(g.display_name || g.filename)}</b>
                  ${duration(g.secs) ? html`<i>${duration(g.secs)}</i>` : null}
                </div>`)}
            </div>
          </div>` : null}
        </div>

        <!-- The sweep's row. Consoles, a rule, then apps; ←/→ walks it as one
             list because it IS one list on the host's side. -->
        <div class="cz-st-wrap" ref=${wrapRef}>
          <div class="cz-st-row" ref=${rowRef}>
            ${systems.flatMap((sy, i) => {
              const cell = html`<${Cell} key=${sy.id} sy=${sy} on=${i === idx}
                                         onClick=${() => (i === idx ? onActivate(i % perPage)
                                           : (Math.floor(i / perPage) === page ? sdk.nav.setGridFocus(i % perPage) : onPage(Math.floor(i / perPage))))} />`
              return i === firstApp && i > 0
                ? [html`<div class="cz-st-sep" key="sep" aria-hidden="true"><span>Apps</span></div>`, cell]
                : [cell]
            })}
          </div>
        </div>

        <div class="cz-foot">
          <div class="cz-count">
            ${totals.games} games on ${totals.systems} systems, ${totals.hours} h played
          </div>
          <div class="cz-keys">
            <${PadKey} k="← →" /><span>Move</span>
            <${PadKey} k="✕" /><span>${app ? (heldApp ? 'Resume' : 'Open') : 'Open'}</span>
            ${heldApp ? html`<${PadKey} k="△" /><span>Close</span>` : null}
            ${!app && lastName ? html`<${PadKey} k="△" /><span>Resume</span>` : null}
            <${PadKey} k="□" /><span>Controller</span>
          </div>
        </div>
      </div>`
  }
}
