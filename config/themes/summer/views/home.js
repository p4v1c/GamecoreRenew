/**
 * The dashboard's look — and only its look.
 *
 * Everything this used to own (page arithmetic, d-pad bindings, launching) now
 * comes from the host, which hands it down as props. That is deliberate: when
 * the theme reimplemented navigation it drifted from the default — running off
 * the right of a row stopped dead instead of turning the page. A view that
 * cannot navigate cannot navigate differently.
 *
 * Props: see frontend/src/components/HomeScreen/types.ts
 */
const fmt = (secs) => {
  if (!secs) return '0m'
  const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60)
  return h ? `${h}h ${m}m` : `${m}m`
}

/** The console's own logo — §3.3: 64x64, on a pad of the system's accent. */
const Logo = (html) => (sy) => {
  const file = sy.iconPath ? String(sy.iconPath).split('/').pop() : null
  // Missing logo falls back to the platform's 1-3 letters, per §3.3 empty states.
  const letters = (sy.platform || sy.label || '??').slice(0, 3).toUpperCase()
  return html`
    <span class="sm-sq">
      ${file
        ? html`<img src=${`/assets/logos/${file}`} alt=""
                    onError=${(e) => { e.target.style.display = 'none' }} />`
        : letters}
    </span>`
}

export const createHomeView = (sdk) => {
  const { html, useMemo } = sdk.ui
  const logo = Logo(html)

  return ({ systems, playtime, counts, focusIdx, page, pageCount, perPage, totals, onActivate, onPage }) => {
    // The brief's fourth stat cell. The dashboard has no per-game history, so
    // it names the system you touched last — the same fact at the resolution
    // this screen actually holds.
    const last = useMemo(() => {
      let best = null
      for (const sy of systems) {
        const at = playtime[sy.id]?.last_played
        if (at && (!best || at > best.at)) best = { at, label: sy.label || sy.id }
      }
      return best?.label || '—'
    }, [systems, playtime])

    return html`
    <div class="sm-home">
      <div class="sm-stats">
        <div><span>SYSTEMS</span><b>${totals.systems}</b></div>
        <div><span>GAMES</span><b>${totals.games}</b></div>
        <div><span>PLAYED</span><b>${totals.hours}h</b></div>
        <div><span>LAST</span><b class="sm-stat-title">${last}</b></div>
      </div>

      <!-- Every page is rendered side by side on one rail, and the rail slides.
           Swapping the contents of a single grid is a hard cut; the default
           dashboard slides, and paging should feel the same in both. -->
      <div class="sm-grid-view">
        <div class="sm-grid-track" style=${{ '--sm-page': String(page) }}>
          ${Array.from({ length: Math.max(pageCount, 1) }, (_, p) => html`
            <div key=${p} class="sm-grid">
              ${systems.slice(p * perPage, (p + 1) * perPage).map((sy, i) => html`
                <div key=${sy.id} class="sm-tile"
                     data-on=${p === page && focusIdx === i ? '1' : '0'}
                     data-empty=${(counts[sy.id] ?? 0) === 0 ? '1' : '0'}
                     onClick=${() => { if (p === page) onActivate(i); else onPage(p) }}
                     style=${{ '--tile-accent': sy.color || '#1D7E93' }}>
                  <div class="sm-tile-head">
                    ${logo(sy)}
                    <span class="sm-badge">${sy.platform || ''}</span>
                  </div>
                  <div class="sm-tile-name">${sy.label}</div>
                  <div class="sm-tile-meta">
                    ${(counts[sy.id] ?? 0) === 0
                      ? 'No games'
                      : `${counts[sy.id]} games · ${fmt(playtime[sy.id]?.total_secs)}`}
                  </div>
                  <i class="sm-tile-rule" />
                  <span class="sm-tile-caret">▸</span>
                </div>`)}
            </div>`)}
        </div>
      </div>

      <div class="sm-dots">
        ${Array.from({ length: Math.max(pageCount, 1) }, (_, i) => html`
          <span key=${i} class="sm-dot" data-on=${i === page ? '1' : '0'} />`)}
      </div>

      <div class="sm-hint">↑↓←→ Navigate · L1/R1 Page · ✕ Open · □ Controller</div>
    </div>`
  }
}
