/**
 * The shelf: spines on the wall, the selected box turned to face you and
 * flippable, a card with the cartridge and its details, ✕ slots it in.
 *
 * R2 cycles three stackings: shelf (upright spines), stack (a pile, index on
 * the left), gallery (flat row, card as a bottom strip).
 *
 * Scrolling, sorting, searching, launching and ○ arrive as props — the host
 * decides them. The art follows `detailGame`, which lags the cursor by 150 ms
 * so a fast scroll does not queue a scrape per game.
 * Props: frontend/src/components/LibraryScreen/types.ts
 */
import { LETTERS, initial, title, stamp, released, played, day } from '../lib/names.js'
import { sample, hexToHsl, vars, NEUTRAL } from '../lib/accent.js'
import { jacket } from '../lib/dossier.js'
import { createUseSwap } from '../lib/swap.js'
import { isPc } from '../lib/pc.js'

/**
 * The fewest spines that may stand either side of the cursor.
 *
 * Each one is a real `box-spine`, so the row is a request count as much as a
 * pixel count. The slots are keyed by filename: the rail slides, the nodes
 * persist, and a scroll costs one new image per step rather than a screenful.
 *
 * This is a floor, not the count — see `reach` below for why a constant cannot
 * be the count.
 */
const MIN_REACH = 12

/**
 * How many columns the mounted row must extend so nothing mounts or drops
 * while the rail is mid-slide (the only way a spine appears to move on its
 * own). Measured, not fixed: half the stage in columns, plus one off-screen.
 * The pitch is read from the rail (it differs per mode); `stack` runs
 * vertically, so its span is the stage height. At 1080p: 19 columns a side.
 */
const railReach = (stage, rail, mode) => {
  if (!stage || !rail) return MIN_REACH
  const declared = parseFloat(
    getComputedStyle(rail).getPropertyValue('--pitch'))
  const pitch = declared > 0 ? declared : 40
  const span = mode === 'stack' ? stage.clientHeight : stage.clientWidth
  if (!span) return MIN_REACH
  return Math.max(MIN_REACH, Math.ceil(span / 2 / pitch) + 1)
}

const SORT_LABEL = { name: 'A–Z', lastPlayed: 'Recently played', playtime: 'Most played' }

/**
 * How far the spine in column `i` is tilted.
 *
 * Stable per position, and much smaller than it looks like it should be,
 * because the row has almost no room: a spine is 34px wide on a 40px pitch, so
 * there are six pixels between one and the next. A spine pivots on its bottom
 * edge, and it is 320px tall — every degree of lean throws its top sideways by
 * 5.6px. Two neighbours leaning a couple of degrees towards each other close a
 * 6px gap several times over and pass straight through one another, which is
 * what a shelf cannot do and what the previous ±3° pattern did constantly.
 *
 * So the budget is the geometry: the step between neighbours must stay under
 * 6 / 5.6 ≈ 1.07°. Two sine waves whose periods do not divide each other keep
 * it from reading as a repeat while holding the largest step to ~0.86° and the
 * whole range to ±0.75° — about four pixels of sway at the top of a spine.
 * Small, but a row of exactly upright rectangles reads as a printed pattern
 * rather than as objects somebody put away, and four pixels is enough.
 *
 * It is a function rather than a literal in the markup because the jacket
 * coming back has to land at the angle of the column it lands in: if the two
 * ever drift apart, a box arrives standing straight between two leaning
 * neighbours and the three look like they are being crushed together.
 */
const lean = (i) => Math.sin(i * 0.9) * 0.45 + Math.sin(i * 1.53) * 0.3

/** Boot: the cartridge rises, the iris closes on the label, the screen settles.
 *
 * The three together are what `launch.ms` in theme.json must equal — the host
 * holds the launch for exactly that long, and everything past it is animation
 * the emulator interrupts.
 *
 * `DARK_MS` is the one that was missing. Rise and iris were 1520ms and so was
 * the declared hold, which meant the call went out on the very frame the iris
 * finished: the last thing the animation does is close to a point, and the
 * screen changed on the same tick, so it never read as "closed" — it read as
 * cut off. A beat of settled black after it is what makes the boot look like it
 * ended rather than like it was interrupted.
 */
const RISE_MS = 900
const IRIS_MS = 620
const DARK_MS = 260
export const BOOT_MS = RISE_MS + IRIS_MS + DARK_MS

export const createLibraryView = (sdk, { accent, useBrowse, useDossier, useSwap: injected, Box, Cartridge }) => {
  // Injected like the others so a test or a fork can replace the motion; the
  // theme's own when nobody does (the vitest harnesses build the view by hand).
  const useSwap = injected || createUseSwap(sdk)
  const { html, useState, useEffect, useMemo, useRef } = sdk.ui
  // Controller button prompts from the host; plain text on an older host.
  const PadKey = sdk.ui.PadKey || (({ k }) => html`<kbd>${k}</kbd>`)
  const PadHints = sdk.ui.PadHints || (({ text }) => text)

  return ({
    systemId, system, games, totalCount, playtime, selectedIdx, detailGame,
    sort, search, loading, loadError, launching, color,
    onSelect, onSearch, onSort, onLaunch, onBack, onRetry,
  }) => {
    const browse = useBrowse({ selectedIdx, count: games.length, launching, onSelect })
    const dossier = useDossier(systemId, detailGame?.filename || '')
    const screen = sdk.nav.use((s) => s.screen)

    // ── the colour the room is wearing ───────────────────────────────────
    // Read out of the jacket, falling back to the system's own accent, and
    // only ever set while this screen is the one on show — the dashboard is
    // still mounted behind it and owns the wall when it is.
    const [tone, setTone] = useState(NEUTRAL)
    useEffect(() => {
      let live = true
      const fallback = hexToHsl(color) || NEUTRAL
      if (!detailGame) { setTone(fallback); return }
      sample(jacket(systemId, detailGame.filename)).then((t) => {
        if (live) setTone(t || fallback)
      })
      return () => { live = false }
    }, [systemId, detailGame?.filename, color])
    useEffect(() => { if (screen === 'library') accent.set(tone) }, [tone, screen])

    // ── the alphabet rail ────────────────────────────────────────────────
    // Only meaningful while the list is alphabetical: under "most played" the
    // letters are scattered, and a rail that points nowhere is worse than no
    // rail. It goes away and the sort takes its place.
    const index = useMemo(() => {
      const first = new Map()
      games.forEach((g, i) => {
        const l = initial(g.display_name)
        if (!first.has(l)) first.set(l, i)
      })
      return first
    }, [games])

    const here = games.length ? initial(games[selectedIdx]?.display_name) : null

    // ── the boot sequence ────────────────────────────────────────────────
    const [phase, setPhase] = useState(null)
    useEffect(() => {
      if (!launching) { setPhase(null); return }
      setPhase('rise')
      const timers = [
        setTimeout(() => setPhase('iris'), RISE_MS),
        setTimeout(() => setPhase('dark'), RISE_MS + IRIS_MS),
      ]
      return () => timers.forEach(clearTimeout)
    }, [launching])

    // Measured after the commit that lays the stage out, and again whenever
    // the stacking or the screen changes size — those are the only two things
    // that move it. No observer: reading `clientWidth` settles the layout by
    // itself, and an effect runs after the DOM is in place, so the value is
    // the one on screen. The first render uses the floor and the second the
    // measurement, which is a mount, not a scroll.
    const stageRef = useRef(null)
    const railRef = useRef(null)
    const [reach, setReach] = useState(MIN_REACH)
    useEffect(() => {
      const measure = () => setReach(railReach(stageRef.current, railRef.current, browse.mode))
      measure()
      window.addEventListener('resize', measure)
      return () => window.removeEventListener('resize', measure)
    }, [browse.mode, loading, loadError, games.length === 0])

    const from = Math.max(0, selectedIdx - reach)
    const to = Math.min(games.length, selectedIdx + reach + 1)
    const shown = games.slice(from, to)

    const meta = dossier.meta
    const media = dossier.media
    const mark = detailGame ? stamp(detailGame.filename) : { region: null, std: null }
    const pt = detailGame ? playtime[detailGame.filename] : null

    // The jacket in your hand and any still going back into the row. Which
    // ones exist is state; where each one is, frame by frame, is lib/swap.js.
    const swap = useSwap({ systemId, games, selectedIdx, mode: browse.mode,
                           flipped: browse.flipped, railRef, lean })

    // ── states before there is a shelf ───────────────────────────────────
    if (loading || loadError || !games.length) {
      return html`
        <div class="cz-lib" data-view="shelf" style=${vars(tone)}>
          <div class="cz-empty">
            ${loading ? html`
              <div class="cz-empty-body">
                <b>Reading the shelf…</b>
                <i>${system?.label || systemId}</i>
              </div>` : null}

            ${!loading && loadError ? html`
              <div class="cz-empty-body">
                <b>The backend did not answer</b>
                <i>Nothing was lost. Try again once it is back.</i>
                <button class="cz-btn" onClick=${onRetry}>Try again</button>
              </div>` : null}

            ${!loading && !loadError ? html`
              <div class="cz-empty-body">
                <b>${totalCount === 0 ? 'This shelf is empty' : 'Nothing matches that'}</b>
                <i>${totalCount === 0
                  ? `Drop ROMs into ${system?.romsPath || 'the system’s folder'} and they appear here.`
                  : `${totalCount} games on the shelf, none called “${search}”.`}</i>
                <button class="cz-btn" onClick=${totalCount === 0 ? onBack : () => onSearch('')}>
                  ${totalCount === 0 ? 'Back to systems' : 'Clear the search'}
                </button>
              </div>` : null}
          </div>
        </div>`
    }

    return html`
      <div class="cz-lib" data-view=${browse.mode} data-booting=${phase ? '1' : '0'}
           style=${vars(tone)}>

        <div class="cz-head">
          <!-- Searching is the host's: the triangle opens its on-screen
               keyboard, which owns the modal stack and the d-pad. This bar
               shows the query and names the button that opens it; the field
               is for a mouse, and calls the same onSearch the keyboard does. -->
          <div class="cz-search" data-live=${search ? '1' : '0'}>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
            </svg>
            <input value=${search} placeholder="Search this shelf"
                   onChange=${(e) => onSearch(e.target.value)} />
            ${search
              ? html`
                <span class="cz-search-n">${games.length}/${totalCount}</span>
                <button class="cz-search-x" onClick=${() => onSearch('')}
                        aria-label="Clear the search">×</button>`
              : html`<${PadKey} k="△" />`}
          </div>

          <div class="cz-rail-index" data-live=${sort === 'name' ? '1' : '0'}>
          ${sort === 'name'
            ? LETTERS.map((l) => html`
              <button key=${l} class="cz-letter"
                      data-on=${l === here ? '1' : '0'}
                      data-has=${index.has(l) ? '1' : '0'}
                      disabled=${!index.has(l)}
                      onClick=${() => index.has(l) && onSelect(index.get(l))}>${l}</button>`)
            : html`
              <span class="cz-sortnote">
                ${SORT_LABEL[sort]}
                <button class="cz-sortback" onClick=${() => onSort('name')}>back to A–Z</button>
              </span>`}
          </div>

          <div class="cz-sortchip">
            <${PadKey} k="L1 R1" /> ${SORT_LABEL[sort]}
          </div>
        </div>

        <div class="cz-body">
          <div class="cz-stage" ref=${stageRef}>
            <div class="cz-shelfline" aria-hidden="true" />

            <div class="cz-rail" ref=${railRef} style=${{ '--i': String(selectedIdx) }}>
              ${shown.map((g, k) => {
                const i = from + k
                return html`
                  <div key=${g.filename} class="cz-slot"
                       style=${{ '--o': String(i), '--lean': `${lean(i).toFixed(2)}deg` }}
                       data-on=${i === selectedIdx ? '1' : '0'}
                       data-gap=${swap.out(g.filename) ? '1' : '0'}>
                    <${Box.Spine} systemId=${systemId} game=${g} on=${i === selectedIdx}
                                  onClick=${() => onSelect(i)} />
                  </div>`
              })}
            </div>

            <div class="cz-castshadow" aria-hidden="true" />

            <!-- Every jacket on stage: the one in your hand and any still on
                 their way back into the row (lib/swap.js moves them).
                 Three nested elements, because the gesture is three things at
                 once and each needs a layer that can carry it: the holder holds
                 the perspective (and must never fade: opacity there groups the
                 scene), the carry travels through that perspective
                 (preserve-3d), and the solid turns on its own axis inside it.
                 Each is keyed on the game it draws and never re-keyed while it
                 moves, so its images are not torn down mid-flight.
                 NO BACKTICKS IN HERE — see scripts/check-theme.mjs. -->
            ${swap.keys.map((key) => {
              const g = games.find((x) => x.filename === key)
              if (!g) return null
              const mine = detailGame?.filename === key
              return html`
                <div class="cz-hold" key=${'jacket:' + key} data-game=${key} aria-hidden=${key === games[selectedIdx]?.filename ? 'false' : 'true'}>
                  <div class="cz-carry" ref=${swap.bind(key)}>
                    <${Box.Face} key=${key} systemId=${systemId} game=${g}
                                 meta=${mine ? meta : null} media=${mine ? media : null}
                                 flipped=${swap.flipOf(key)} />
                  </div>
                </div>`
            })}
          </div>

          <!-- the card: beside the shelf, or a strip along the bottom -->
          <div class="cz-card" key=${detailGame?.filename || 'none'}>
            <div class="cz-card-media">
              <${Cartridge} systemId=${systemId} game=${detailGame} media=${media} size="card" />
            </div>

            <div class="cz-card-text">
              <div class="cz-card-head">
                <h2 class="cz-card-name">${title(detailGame?.display_name || '')}</h2>
                <div class="cz-stamps">
                  ${mark.std ? html`<span class="cz-stamp cz-stamp-std">${mark.std}</span>` : null}
                  ${mark.region ? html`<span class="cz-stamp">${mark.region}</span>` : null}
                  ${!mark.std && !mark.region
                    ? html`<span class="cz-stamp">${isPc(systemId) ? 'PC' : (String(detailGame?.ext || '').replace('.', '').toUpperCase() || 'ROM')}</span>`
                    : null}
                </div>
              </div>

              <dl class="cz-specs" data-loading=${dossier.loading ? '1' : '0'}>
                <div><dt>Released</dt><dd>${released(meta)}</dd></div>
                <div><dt>Developer</dt><dd>${meta?.developer || '—'}</dd></div>
                <div><dt>Publisher</dt><dd>${meta?.publisher || '—'}</dd></div>
                <div><dt>Genre</dt><dd>${meta?.genres?.[0] || '—'}</dd></div>
                <div><dt>Players</dt><dd>${meta?.players_label || (meta?.players ? String(meta.players) : '—')}</dd></div>
              </dl>

              <dl class="cz-specs cz-specs-log">
                <div><dt>Play time</dt><dd>${played(pt?.total_secs)}</dd></div>
                <div><dt>Last played</dt><dd>${day(pt?.last_played)}</dd></div>
              </dl>
            </div>
          </div>
        </div>

        <div class="cz-foot">
          <div class="cz-count">
            ${phase ? 'Booting selected cartridge'
              : search ? `${games.length} of ${totalCount} games match “${search}”`
                : `${totalCount} games indexed`}
          </div>

          <div class="cz-keys">
            <${PadKey} k="← →" /><span>Scroll</span>
            <${PadKey} k="L2" /><span>Flip</span>
            <${PadKey} k="R2" /><span>${browse.modeLabel}</span>
            <${PadKey} k="△" /><span>Search</span>
            <${PadKey} k="Options" /><span>Game options</span>
            <${PadKey} k="✕" /><span>Start</span>
            <${PadKey} k="○" /><span>Back</span>
          </div>
        </div>

        <!-- Outside the stage on purpose: the stage carries a perspective, and
             a fixed layer inside a transformed ancestor is not fixed at all. -->
        ${phase ? html`
          <div class="cz-boot" data-phase=${phase}>
            <div class="cz-boot-iris">
              <${Cartridge} systemId=${systemId} game=${detailGame || games[selectedIdx]}
                            media=${media} size="boot" />
            </div>
          </div>` : null}
      </div>`
  }
}
