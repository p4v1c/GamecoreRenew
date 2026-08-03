/**
 * The library's look: the game list as a column of glass cards, the selected
 * game blown up beside it over the ocean.
 *
 * Not in the design brief — the mockup only ever showed the dashboard. Built in
 * the same language: glass over water, mandarin focus ring, no new navigation.
 *
 * Behaviour is the host's. Scrolling, sorting, searching and launching arrive
 * as props, so this list moves exactly like the default one.
 * Props: frontend/src/components/LibraryScreen/types.ts
 */
const SORT_LABELS = { name: 'A–Z', lastPlayed: 'Recent', playtime: 'Played' }
// Display order is the brief's, which is not the host's enum order.
const SORT_KEYS = ['name', 'lastPlayed', 'playtime']

// The host's Chip paints itself from a hex, so a neutral one gives the glass
// chips the brief asks for instead of a wash of the system's accent.
const CHIP_INK = '#EFE6D6'

const fmt = (secs) => {
  if (!secs) return '—'
  const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60)
  return h ? `${h}h ${m}m` : `${m}m`
}

const date = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString()
}

// Long ROM names carry scene tags the player did not ask for.
const clean = (name) => String(name || '')
  .replace(/\.[a-z0-9]{2,4}$/i, '')
  .replace(/\s*[\(\[][^\)\]]*[\)\]]/g, '')
  .trim() || String(name || '')

import { createBox3D, isTurnable } from './box3d.js'

// Captures under the description. `screenshot-gameplay` is the in-game one and
// `screenshot-game-title` the title screen; both are common, and showing the
// title screen alone would look like a mistake, so gameplay leads.
const SHOT_TYPES = ['screenshot-gameplay', 'screenshot-game-title']
const MAX_SHOTS = 2

export const createLibraryView = (sdk) => {
  const { html, useEffect, useRef, useState } = sdk.ui
  const Box3D = createBox3D(sdk)

  /**
   * Everything this game has, in one request.
   *
   * One per selected game, and the host already debounces the selection by
   * 150 ms, so scrolling a long system does not fire one per step. The box art
   * and the captures both read from this — asking twice for the same catalogue
   * would double the cost of moving the cursor.
   *
   * It degrades quietly in all three ways it can fail: an older host has no
   * `sdk.api.media`, a box with no scraper account answers `available: false`,
   * and a game can simply have nothing. All three end as `null`, which every
   * consumer below already treats as "show the plain cover".
   */
  const useMedia = (systemId, filename) => {
    const [media, setMedia] = useState(null)
    useEffect(() => {
      setMedia(null)
      if (!sdk.api.media || !filename) return
      let cancelled = false
      sdk.api.media.list(systemId, filename)
        .then((idx) => { if (!cancelled && idx?.found) setMedia(idx.media || null) })
        .catch(() => {})
      return () => { cancelled = true }
    }, [systemId, filename])
    return media
  }

  return ({
    systemId, system, games, totalCount, playtime, selectedIdx, detailGame,
    sort, search, loading, loadError, launching, color,
    onSelect, onSearch, onSort, onLaunch, onBack, onRetry, Cover, Meta,
  }) => {
    // The pad moves the selection; the list has to follow it, or a long system
    // scrolls the focus straight out of view.
    const listRef = useRef(null)
    useEffect(() => {
      const row = listRef.current?.querySelector('[data-on="1"]')
      row?.scrollIntoView({ block: 'nearest' })
    }, [selectedIdx])

    const pt = detailGame ? playtime[detailGame.filename] : null
    const media = useMedia(systemId, detailGame?.filename)
    const shots = (media ? SHOT_TYPES.filter(t => media[t]) : []).slice(0, MAX_SHOTS)
      .map(t => ({ type: t, url: sdk.api.media.url(systemId, detailGame.filename, t) }))

    return html`
      <div class="sm-lib" style=${{ '--sys-accent': color }}>
        <div class="sm-lib-head">
          <button class="sm-lib-back" onClick=${onBack}>‹ Home</button>
          <span class="sm-lib-logo">
            ${system?.iconPath
              ? html`<img src=${`/assets/logos/${String(system.iconPath).split('/').pop()}`} alt=""
                          onError=${(e) => { e.target.style.display = 'none' }} />`
              : (system?.platform || systemId).slice(0, 3).toUpperCase()}
          </span>
          <div class="sm-lib-title">
            <b>${system?.label || system?.platform || systemId}</b>
            <i>${totalCount} games</i>
          </div>
          <div class="sm-lib-spacer" />
          <div class="sm-lib-search">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none"
                 stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
            </svg>
            <input value=${search} placeholder="Search…"
                   onChange=${(e) => onSearch(e.target.value)} />
          </div>
          <div class="sm-lib-sorts">
            ${SORT_KEYS.map(k => html`
              <button key=${k} class="sm-lib-sort" data-on=${sort === k ? '1' : '0'}
                      onClick=${() => onSort(k)}>${SORT_LABELS[k]}</button>`)}
          </div>
        </div>

        <div class="sm-lib-body">
          <div class="sm-lib-list" ref=${listRef}>
            ${loading ? html`<div class="sm-lib-empty">Loading…</div>` : null}
            ${!loading && loadError ? html`
              <div class="sm-lib-empty">
                <div class="sm-lib-err">Could not reach backend</div>
                <button class="sm-lib-retry" onClick=${onRetry}>Retry</button>
              </div>` : null}
            ${!loading && !loadError && games.length === 0 ? html`
              <div class="sm-lib-empty">${totalCount === 0 ? 'No ROMs found' : 'No results'}</div>` : null}
            ${games.map((g, i) => html`
              <div key=${g.filename} class="sm-lib-row" data-on=${i === selectedIdx ? '1' : '0'}
                   onClick=${() => onSelect(i)}>
                <span class="sm-lib-row-main">
                  <b>${clean(g.display_name)}</b>
                  <i>${g.ext}</i>
                </span>
                <span class="sm-lib-row-time">
                  <b>${fmt(playtime[g.filename]?.total_secs)}</b>
                  <i>${date(playtime[g.filename]?.last_played)}</i>
                </span>
              </div>`)}
          </div>

          ${detailGame ? html`
            <div class="sm-lib-detail" key=${detailGame.filename}>
              <!-- The box, what you have done with it, and what you came to do.
                   All three belong to the game as an object, so they sit in one
                   column under it — which also gives the captures the whole
                   height of the other one. -->
              <div class="sm-lib-side">
                <div class="sm-lib-cover">
                  <${Box3D} systemId=${systemId} filename=${detailGame.filename}
                            media=${media} color=${color} Cover=${Cover} />
                </div>
                <div class="sm-lib-stats">
                  <div><span>PLAY TIME</span><b>${fmt(pt?.total_secs)}</b></div>
                  <div><span>LAST PLAYED</span><b>${date(pt?.last_played) || '—'}</b></div>
                </div>
                <button class="sm-lib-play" data-busy=${launching ? '1' : '0'} onClick=${onLaunch}>
                  ${launching ? '⏳ Launching…' : '▶ Play'}
                </button>
              </div>
              <div class="sm-lib-info">
                <div class="sm-lib-sys">${(system?.label || system?.platform || systemId).toUpperCase()}</div>
                <h2 class="sm-lib-name">${clean(detailGame.display_name)}</h2>
                <${Meta} systemId=${systemId} filename=${detailGame.filename}
                         color=${CHIP_INK} extChip=${html`<span class="sm-lib-chip">${detailGame.ext}</span>`} />
                <!-- The image is the frame. A wrapper would have to pick a
                     size before knowing the picture's shape, and whatever it
                     picked would be wrong for one console or the other —
                     which is how a 16:9 capture ended up centred in a tall
                     empty square. -->
                ${shots.length ? html`
                  <div class="sm-lib-shots">
                    ${shots.map(s => html`
                      <img key=${s.type} class="sm-lib-shot" src=${s.url} alt="" loading="lazy"
                           onError=${(e) => { e.target.style.display = 'none' }} />`)}
                  </div>` : null}
              </div>
            </div>` : null}
        </div>

        <!-- The drift makes the box look turnable; this says so. It appears
             only when the game really has the faces to turn, because a hint
             for something that does not work is worse than no hint. -->
        <div class="sm-hint sm-lib-hint">
          ↑↓ Navigate · ✕ Play · △ Search · □ Controller · L1/R1 Sort${
            isTurnable(media) ? ' · ⟳ R-Stick Turn box' : ''} · ○ Back
        </div>
      </div>`
  }
}
