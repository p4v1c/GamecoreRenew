/**
 * The shelf. This is the screen the theme exists for.
 *
 * A system's games stand as spines on a papered wall; the selected one is
 * turned to face you and can be flipped over; a card beside it shows the
 * cartridge and its printing details; ✕ slots the cartridge in.
 *
 * Three ways of stacking the same shelf, cycled with R2:
 *   shelf    spines upright, the turned box among them, card at the right
 *   stack    the boxes lying in a pile, index down the left edge
 *   gallery  spines flat-on in a straight row, the card as a strip along the
 *            bottom — the reading position, right before you press start
 *
 * ── What is the host's, and stays the host's ───────────────────────────────
 * Scrolling, sorting, searching, launching and ○ arrive as props. Nothing here
 * decides any of them, which is why a shelf and the default list behave
 * identically and only the picture differs. The two things this file does add
 * — turning the box over, and changing how it is stacked — move no selection
 * and survive no reload.
 *
 * ── Why the art follows the *settled* selection ────────────────────────────
 * `detailGame` lags `selectedIdx` by 150 ms, on purpose: a jacket that has
 * never been fetched costs a scrape, so a fast scroll through four hundred
 * games would otherwise queue four hundred of them. The turned box never
 * moves — it is centred in the stage, outside the rail — so the lag reads as
 * the artwork settling, not as the shelf stuttering.
 *
 * Props: frontend/src/components/LibraryScreen/types.ts
 */
import { LETTERS, initial, title, stamp, released, played, day } from '../lib/names.js'
import { sample, hexToHsl, vars, NEUTRAL } from '../lib/accent.js'
import { jacket } from '../lib/dossier.js'

/**
 * How many spines exist on either side of the cursor.
 *
 * Each one is a real `box-spine`, so the window is a request count as much as
 * a pixel count. It is deliberately small and the slots are keyed by filename:
 * the rail slides, the nodes persist, and a scroll costs one new image per
 * step rather than a fresh screenful.
 */
const WINDOW = 12

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

/** Boot: the cartridge rises, then the iris closes on the label. */
const RISE_MS = 900
const IRIS_MS = 620

/** The whole swap: the jacket going back in, then the next one coming out.
 *  Must match theme.css — 360ms of `cz-push-*`, then 440ms of `cz-pull-*` after
 *  a delay of the same 360. The outgoing node is dropped only at the end of all
 *  of it, so `--dir` cannot change halfway through the second animation, and a
 *  jacket cannot be unmounted mid-gesture and read as never having folded. */
const PUSH_MS = 360
const PULL_MS = PUSH_MS + 440

export const createLibraryView = (sdk, { accent, useBrowse, useDossier, Box, Cartridge }) => {
  const { html, useState, useEffect, useMemo, useRef } = sdk.ui

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

    const from = Math.max(0, selectedIdx - WINDOW)
    const to = Math.min(games.length, selectedIdx + WINDOW + 1)
    const shown = games.slice(from, to)

    const meta = dossier.meta
    const media = dossier.media
    const mark = detailGame ? stamp(detailGame.filename) : { region: null, std: null }
    const pt = detailGame ? playtime[detailGame.filename] : null
    const settled = detailGame && games[selectedIdx]?.filename === detailGame.filename

    // The jacket that is on its way back into the shelf.
    //
    // Held for exactly as long as the animation lasts, then dropped: a stale
    // node left mounted would keep its `Face` — and its images — alive for
    // every game you ever walked past. The timer is cleared on the way out, so
    // walking the shelf quickly replaces the outgoing jacket rather than
    // stacking a queue of them.
    // `tucked` says whether the jacket you are moving TO is still standing in
    // the row. It is, for the whole time the previous one is being put away —
    // and while it is, its spine must be drawn like any other, because it IS
    // one. Only when the solid takes over does that column become a hole. This
    // is the difference between a shelf and a diorama with a permanent slot.
    //
    // It lives inside the same object as the departing jacket rather than in a
    // state of its own, and that is not tidiness. Two states meant two timers
    // that could be cleared independently, and the effect has three early
    // returns that register no cleanup: an interrupted swap could leave the
    // flag set with nothing left to clear it, and a stuck `tucked` does not
    // degrade — it hides the jacket outright, for the rest of the session.
    // Hung off the swap, it cannot outlive it: no swap, nothing tucked.
    //
    // The CSS delay on the arriving animation is the same PUSH_MS, so the pose
    // it becomes visible in is the pose it was parked in — one flag flips both
    // sides of the handoff in one render, and they cannot disagree.
    const current = games[selectedIdx]?.filename || null
    const [swap, setSwap] = useState(null)   // { game, dir, tucked }

    const lastRef = useRef({ name: current, idx: selectedIdx })
    useEffect(() => {
      const prev = lastRef.current
      lastRef.current = { name: current, idx: selectedIdx }
      if (!prev.name || prev.name === current) return
      const gone = games.find((g) => g.filename === prev.name)
      if (!gone) { setSwap(null); return }   // the shelf changed under us, not the cursor
      // Which way along the row. The rail keeps the selection at the centre,
      // so after a step forward the jacket you left is one pitch to the LEFT
      // and the one arriving came from one pitch to the right.
      //
      // Unless one is already on its way back. You cannot put a box away and
      // take another out four times a second, and trying to looked like it:
      // the outgoing holder is keyed by filename, so every step unmounted the
      // half-turned jacket and mounted the next one face-on at full size, and
      // holding a direction became a stutter of boxes appearing at the centre
      // and vanishing. Worse, the one in flight was aiming at a column one
      // pitch away, and the rail had already moved two.
      //
      // So a second step cancels the ceremony rather than restarting it: no
      // outgoing jacket, `tucked` held, timers re-armed from this step. What
      // is left is what a shelf actually does — you slide along the row with
      // nothing in your hand, every spine drawn including the selected one,
      // and the jacket comes out of its gap once you stop.
      setSwap((s) => (s ? { game: null, dir: s.dir, tucked: true }
        : { game: gone, dir: selectedIdx > prev.idx ? 1 : -1, tucked: true }))
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
              : html`<kbd>△</kbd>`}
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
            <kbd>L1</kbd><kbd>R1</kbd> ${SORT_LABEL[sort]}
          </div>
        </div>

        <div class="cz-body">
          <div class="cz-stage">
            <div class="cz-shelfline" aria-hidden="true" />

            <div class="cz-rail" style=${{ '--i': String(selectedIdx) }}>
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
              <div class="cz-hold" key=${leaving.game.filename} data-phase="out"
                   style=${{ '--dir': String(leaving.dir),
                             '--lean': `${lean(games.findIndex((g) => g.filename === leaving.game.filename)).toFixed(2)}deg` }}
                   aria-hidden="true">
                <div class="cz-carry">
                  <${Box.Face} key=${leaving.game.filename}
                               systemId=${systemId} game=${leaving.game}
                               meta=${meta} media=${media} flipped=${false} />
                </div>
              </div>` : null}

            <div class="cz-hold" key=${games[selectedIdx]?.filename || 'none'}
                 data-phase="in"
                 style=${{ '--dir': String(swapping?.dir || 1),
                           '--lean': `${lean(selectedIdx).toFixed(2)}deg`,
                           '--wait': swapping ? `${PUSH_MS}ms` : '0ms' }}
                 data-tucked=${tucked ? '1' : '0'}
                 data-turning=${settled ? '0' : '1'}>
              <div class="cz-carry">
                <!-- Keyed on the game it DRAWS, which is not what the wrapper
                     above is keyed on. The cz-hold node keys on the CURSOR,
                     games[selectedIdx], because that is what has to fire the
                     jacket animation. This draws detailGame, the settled
                     selection, 150 ms behind it. So the two disagree for the
                     length of the debounce, and without its own key this
                     component was reused across a change of game: it kept the
                     previous title's measured proportions and drew the new
                     artwork inside them. A different game is a different box.
                     (No backticks in this comment: it sits inside a template
                     literal and one backtick would end it — the rest of the
                     markup then parses as JavaScript and the theme dies.) -->
                <${Box.Face} key=${(detailGame || games[selectedIdx])?.filename || 'none'}
                             systemId=${systemId} game=${detailGame || games[selectedIdx]}
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
                <div><dt>Sessions</dt><dd>${pt?.session_count || '—'}</dd></div>
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
            <kbd>←</kbd><kbd>→</kbd><span>Scroll</span>
            <kbd>L2</kbd><span>Flip</span>
            <kbd>R2</kbd><span>${browse.modeLabel}</span>
            <kbd>△</kbd><span>Search</span>
            <kbd class="cz-key-go">✕</kbd><span>Start</span>
            <kbd>○</kbd><span>Back</span>
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
