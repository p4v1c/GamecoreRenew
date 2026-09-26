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

/** The whole swap: the jacket going back in, then the next one coming out.
 *  Must match theme.css — 360ms of `cz-push-*`, then 560ms of `cz-pull-*` after
 *  a delay of the same 360. The outgoing node is dropped only at the end of all
 *  of it, so `--dir` cannot change halfway through the second animation, and a
 *  jacket cannot be unmounted mid-gesture and read as never having folded.
 *
 *  The pull was 440ms and the turn inside it read as dry — 202ms to cover 90°.
 *  It is 560 now, with the handover moved from 54% to 42% in the keyframes, so
 *  the travel keeps its pace and only the turn is longer. This number and that
 *  one are two files with nothing enforcing the match: shorten the CSS without
 *  shortening this and the outgoing jacket lingers; shorten this without the
 *  CSS and it vanishes mid-turn. */
const PUSH_MS = 360
const PULL_MS = PUSH_MS + 560

export const createLibraryView = (sdk, { accent, useBrowse, useDossier, Box, Cartridge }) => {
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
    const settled = detailGame && games[selectedIdx]?.filename === detailGame.filename

    // The jacket going back into the shelf, kept mounted only for its
    // animation (a stale node would keep every walked-past Face alive).
    // `tucked` = the jacket you are moving TO is still standing in the row and
    // must be drawn as a spine until the solid takes over. It lives on the same
    // object as the departing jacket so it cannot outlive the swap (a stuck
    // flag hides the jacket for the session). The arriving animation's delay
    // ends at PUSH_MS from the press, so one flag flips both sides at once.
    const current = games[selectedIdx]?.filename || null
    const [swap, setSwap] = useState(null)   // { game, dir, tucked, at }

    const lastRef = useRef({ name: current, idx: selectedIdx })
    useEffect(() => {
      const prev = lastRef.current
      lastRef.current = { name: current, idx: selectedIdx }
      if (!prev.name || prev.name === current) return
      const gone = games.find((g) => g.filename === prev.name)
      if (!gone) { setSwap(null); return }   // the shelf changed under us, not the cursor
      // Direction along the row: after a step forward, the jacket you left is
      // one pitch LEFT and the arriving one came from the right.
      //
      // A second step while nothing is out yet cancels the ceremony (no
      // outgoing jacket, `tucked` held, timers re-armed): you slide along the
      // row empty-handed and the jacket comes out when you stop. Once a jacket
      // IS out (`tucked` false), a press is a normal step, never a cancel —
      // cancelling then emptied the shelf. Known cost: a press during the pull
      // jumps the box to face-on before it folds away.
      const at = Date.now()
      setSwap((s) => (s && s.tucked
        ? { game: null, dir: s.dir, tucked: true, at }
        : { game: gone, dir: selectedIdx > prev.idx ? 1 : -1, tucked: true, at }))
      const timers = [
        setTimeout(() => setSwap((s) => (s ? { ...s, tucked: false } : s)), PUSH_MS),
        setTimeout(() => setSwap(null), PULL_MS),
      ]
      return () => timers.forEach(clearTimeout)
    }, [current])

    // Two different questions, and conflating them is what would crash on a
    // cancelled ceremony. `swapping` is "is a change in progress" — it governs
    // the wait before the next jacket comes out, and it survives a cancellation.
    // `leaving` is "there is a jacket to animate out", which a cancelled step
    // no longer has. A swap whose game has vanished from the shelf underneath
    // us is not one either.
    const swapping = swap && (!swap.game || games.some((g) => g.filename === swap.game.filename))
      ? swap : null
    const leaving = swapping?.game ? swapping : null
    const tucked = !!swapping?.tucked

    /**
     * One clock for the whole arriving gesture.
     *
     * The travel lives on `.cz-carry` and the turn on `.cz-box` inside it, and
     * they used to start at different moments: the holder was keyed on the
     * CURSOR and mounted on the press, while the solid was keyed on the
     * SETTLED selection and therefore replaced 150 ms later — a fresh node
     * with a fresh animation. Measured in a browser, half a second after a
     * step: 500 ms elapsed on the travel and 333 ms on the turn. The box had
     * set off down the shelf and was still standing edge-on, then caught up in
     * a hurry.
     *
     * Both are keyed on the same thing now — the game actually drawn — so the
     * solid is never replaced underneath a running animation, and the two
     * halves cannot drift apart by construction.
     *
     * The lag has to be paid back somewhere, and it is paid here: `--wait` is
     * the CSS delay that lets the outgoing jacket finish first, so the arrival
     * subtracts the time already spent. Frozen for the life of the node — a
     * delay edited on a running animation restarts it, which is the defect
     * again with a different cause.
     */
    const inGame = detailGame || games[selectedIdx]
    const inKey = inGame?.filename || 'none'
    const waitRef = useRef({ key: null, ms: 0 })
    if (waitRef.current.key !== inKey) {
      const spent = swapping ? Math.max(0, Date.now() - swapping.at) : 0
      waitRef.current = { key: inKey, ms: swapping ? Math.max(0, PUSH_MS - spent) : 0 }
    }

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
                       data-gap=${(i === selectedIdx && !tucked)
                                  || g.filename === leaving?.game?.filename ? '1' : '0'}>
                    <${Box.Spine} systemId=${systemId} game=${g} on=${i === selectedIdx}
                                  onClick=${() => onSelect(i)} />
                  </div>`
              })}
            </div>

            <div class="cz-castshadow" aria-hidden="true" />

            <!-- Two jackets while one is replacing the other.
                 A single node keyed on the selection could only animate the
                 arrival: the outgoing box vanished on the same frame, so the
                 jacket appeared to pop rather than to change. Keeping the
                 previous one mounted for the length of the crossfade lets it
                 be pushed back between its neighbours while the new one is
                 drawn out, which is the gesture being described.
                 Both are absolutely positioned in the same holder, so the one
                 leaving takes no space and nothing shifts under it.

                 Three nested elements, not one, because the gesture is three
                 things at once and each has to happen on a layer that can carry
                 it: the holder fades (opacity groups, and grouping flattens),
                 the carry travels (it keeps preserve-3d, so the box moves
                 through the perspective rather than across a picture of it),
                 and the solid inside turns on its own axis. Collapse any two of
                 them and the box stops being a box mid-turn.
                 NO BACKTICKS IN HERE — see the note at the top of theme.css. -->
            ${leaving ? html`
              <div class="cz-hold" key=${`out:${leaving.game.filename}`} data-phase="out"
                   style=${{ '--dir': String(leaving.dir),
                             '--lean': `${lean(games.findIndex((g) => g.filename === leaving.game.filename)).toFixed(2)}deg` }}
                   aria-hidden="true">
                <!-- The phase is part of the key, and that is not decoration.
                     Both holders are keyed on a filename, and for the 150 ms
                     between a press and the artwork settling they are keyed on
                     the SAME one: the jacket being put away is the jacket that
                     was on screen. Two siblings with one key is a list React
                     cannot reconcile — it kept the outgoing node alive through
                     a render that had dropped it, which is a box that folds
                     away and then stays there. -->
                <div class="cz-carry">
                  <${Box.Face} key=${leaving.game.filename}
                               systemId=${systemId} game=${leaving.game}
                               meta=${meta} media=${media} flipped=${false} />
                </div>
              </div>` : null}

            <div class="cz-hold" key=${`in:${inKey}`}
                 data-phase="in"
                 style=${{ '--dir': String(swapping?.dir || 1),
                           '--lean': `${lean(selectedIdx).toFixed(2)}deg`,
                           '--wait': `${waitRef.current.ms}ms` }}
                 data-tucked=${tucked ? '1' : '0'}
                 data-turning=${settled ? '0' : '1'}>
              <div class="cz-carry">
                <!-- Keyed on the game it DRAWS, and so is the holder above it.
                     The key is needed: without it the component was reused
                     across a change of game, kept the previous title's measured
                     proportions and drew the new artwork inside them. A
                     different game is a different box.
                     What changed is the wrapper. It used to key on the CURSOR
                     while this keyed on the SETTLED selection 150 ms behind, so
                     this solid was torn down and rebuilt in the middle of the
                     holder's animation — one gesture on two clocks. Both keys
                     are the same value now, so a new box is a new holder and
                     nothing is replaced mid-flight.
                     (No backticks in this comment: it sits inside a template
                     literal and one backtick would end it — the rest of the
                     markup then parses as JavaScript and the theme dies.) -->
                <${Box.Face} key=${inKey}
                             systemId=${systemId} game=${inGame}
                             meta=${meta} media=${media} flipped=${browse.flipped} />
              </div>
            </div>
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
                    ? html`<span class="cz-stamp">${String(detailGame?.ext || '').replace('.', '').toUpperCase() || 'ROM'}</span>`
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
              : search ? `${games.length} of ${totalCount} games · “${search}”`
                : `${totalCount} games indexed`}
          </div>

          <div class="cz-keys">
            <${PadKey} k="← →" /><span>Scroll</span>
            <${PadKey} k="L2" /><span>Flip</span>
            <${PadKey} k="R2" /><span>${browse.modeLabel}</span>
            <${PadKey} k="△" /><span>Search</span>
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
