/**
 * The game list and its detail panel — markup only.
 *
 * `Cover` and `Meta` arrive ready-made and bound. Redrawing them in a theme
 * means reimplementing the missing-art and 404 paths, which is exactly the
 * work nobody wants to do twice and nobody does identically.
 *
 * Two things here are easy to get wrong and are commented where they happen:
 * the list is driven by `selectedIdx` while the panel is driven by
 * `detailGame`, and `sortKeys` is a prop rather than a list typed out here.
 */
export const createLibraryView = (sdk) => {
  const { html, useEffect, useRef, motion, AnimatePresence } = sdk.ui
  const { gameName, time, date, hexToRgb } = sdk.format

  return ({
    system, games, totalCount, playtime, selectedIdx, detailGame,
    sort, sortKeys, sortLabels, search, loading, loadError, launching, color,
    onSelect, onSort, onLaunch, onBack, onRetry, Cover, Meta, systemId,
  }) => {
    const rgb = hexToRgb(color)
    const listRef = useRef(null)

    // Keep the cursor on screen. The host moves `selectedIdx` from the d-pad
    // and never touches the DOM, so scrolling to it is the view's job — and a
    // themed list that forgets it works perfectly until the eleventh game.
    useEffect(() => {
      const row = listRef.current?.querySelector('[data-sel="1"]')
      if (row) row.scrollIntoView({ block: 'nearest' })
    }, [selectedIdx])

    if (loadError) {
      return html`
        <div class="dr-lib-msg">
          <p>Could not read this system's games.</p>
          <button class="dr-btn" onClick=${onRetry}>Try again</button>
          <button class="dr-btn dr-btn-ghost" onClick=${onBack}>Back</button>
        </div>`
    }

    return html`
      <div class="dr-lib">
        <div class="dr-lib-head">
          <button class="dr-back" onClick=${onBack}>‹</button>
          <div class="dr-lib-title">
            <b style=${{ color }}>${system?.label || systemId}</b>
            <i>${games.length}${games.length !== totalCount ? ` of ${totalCount}` : ''} games${search ? ` · “${search}”` : ''}</i>
          </div>
          <div class="dr-sorts">
            ${/* From props, not a local list: L1/R1 cycle sortKeys inside
                  LibraryScreen, so a copy typed here would draw one set of
                  options while the buttons walked another. */
              sortKeys.map(k => html`
                <button key=${k} class="dr-sort" data-on=${k === sort ? '1' : '0'}
                        style=${k === sort ? { background: `rgba(${rgb},0.22)`, borderColor: `${color}66`, color: '#fff' } : null}
                        onClick=${() => onSort(k)}>${sortLabels[k]}</button>`)}
          </div>
        </div>

        <div class="dr-lib-body">
          <div class="dr-list" ref=${listRef}>
            ${loading
              ? html`<div class="dr-lib-msg"><p>Reading the library…</p></div>`
              : games.length === 0
                ? html`<div class="dr-lib-msg"><p>${search ? 'No game matches that search.' : 'No game in this system yet.'}</p></div>`
                : games.map((g, i) => html`
                    <div key=${g.filename} class="dr-row" data-sel=${i === selectedIdx ? '1' : '0'}
                         style=${i === selectedIdx ? { background: `rgba(${rgb},0.16)`, borderColor: `${color}55` } : null}
                         onClick=${() => (i === selectedIdx ? onLaunch() : onSelect(i))}>
                      <span class="dr-row-name">${gameName(g.display_name)}</span>
                      ${playtime[g.filename]?.total_secs
                        ? html`<span class="dr-row-time">${time(playtime[g.filename].total_secs)}</span>`
                        : null}
                    </div>`)}
          </div>

          <div class="dr-detail">
            <${AnimatePresence} mode="wait">
              ${detailGame ? html`
                <${motion.div} key=${detailGame.filename}
                  initial=${{ opacity: 0, y: 8 }}
                  animate=${{ opacity: 1, y: 0 }}
                  exit=${{ opacity: 0, y: -8 }}
                  transition=${{ duration: 0.18 }}
                  class="dr-detail-in">
                  <div class="dr-cover">
                    <${Cover} filename=${detailGame.filename} systemId=${systemId} color=${color} />
                  </div>
                  <div class="dr-detail-name">${gameName(detailGame.display_name)}</div>
                  ${playtime[detailGame.filename]?.last_played
                    ? html`<div class="dr-detail-sub">Last played ${date(playtime[detailGame.filename].last_played)}</div>`
                    : null}
                  <${Meta} systemId=${systemId} filename=${detailGame.filename} color=${color}
                           extChip=${html`<span class="dr-chip">${detailGame.ext}</span>`} />
                <//>` : null}
            <//>
          </div>
        </div>

        <${AnimatePresence}>
          ${launching ? html`
            <${motion.div} key="launching" class="dr-launching"
              initial=${{ opacity: 0 }} animate=${{ opacity: 1 }} exit=${{ opacity: 0 }}>
              <div class="dr-launching-in" style=${{ borderColor: `${color}66` }}>
                <div class="dr-spinner" style=${{ borderTopColor: color }} />
                <span>Starting ${detailGame ? gameName(detailGame.display_name) : 'the game'}…</span>
                ${/* ○ still means ○: the host cancels the launch and clears
                      this flag under us. Never read it as "the game is up". */
                  html`<i>○ to cancel</i>`}
              </div>
            <//>` : null}
        <//>

        <div class="dr-hint">↑↓ Select · ✕ Launch · △ Search · L1/R1 Sort · ○ Back</div>
      </div>`
  }
}
