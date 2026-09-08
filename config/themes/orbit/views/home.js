import {isApp, systemName, packLogo} from '../lib/artwork.js'

export function createHome(sdk, artwork, sessions, Footer) {
  const {html, useRef, useEffect} = sdk.ui
  const {SystemArt} = artwork
  return function Home({pageItems, focusIdx, totals, counts, onFocus, onActivate, page, pageCount, onPage}) {
    const rail = useRef(null)
    const selected = pageItems[focusIdx]
    const app = isApp(selected)
    const screen = sdk.nav.use((s) => s.screen)
    const {background} = sdk.session.use()
    // An application tile launches with `game_key === system_id`, so that pair
    // is what identifies its session — see routers/games.py.
    const held = selected ? sessions.heldMatch(background, selected.id, selected.id) : null
    useEffect(() => {
      rail.current?.querySelector('[data-active="true"]')?.scrollIntoView({block: 'nearest', inline: 'center', behavior: 'smooth'})
    }, [focusIdx, page, screen])
    return html`<main className="orbit-home">
      <div className="orbit-rail-heading"><span className="orbit-eyebrow">YOUR NEXT ESCAPE</span><span>${pageItems.length ? String(focusIdx + 1).padStart(2, '0') : '00'} / ${String(pageItems.length).padStart(2, '0')}</span></div>
      <div className="orbit-home-rail" ref=${rail} role="list" aria-label="Consoles and applications">
        ${pageItems.map((s, i) => html`<button key=${s.id} className="orbit-tile" role="listitem"
          data-active=${i === focusIdx ? 'true' : 'false'} aria-label=${systemName(s)} aria-current=${i === focusIdx ? 'true' : undefined}
          onFocus=${() => onFocus(i)} onClick=${() => onActivate(i)}>
          <${SystemArt} system=${s} /><span className="orbit-tile-name">${systemName(s)}</span>
          ${sessions.heldMatch(background, s.id, s.id) ? html`<span className="orbit-tile-badge">SUSPENDED</span>` : null}
        </button>`)}
      </div>
      ${pageCount > 1 ? html`<div className="orbit-pages"><button onClick=${() => onPage(Math.max(0, page - 1))}>Previous</button><span>${page + 1} / ${pageCount}</span><button onClick=${() => onPage(Math.min(pageCount - 1, page + 1))}>Next</button></div>` : null}
      ${selected ? html`<section className="orbit-home-feature" key=${selected.id}>
        <div className="orbit-feature-copy"><span className="orbit-eyebrow">${app ? 'APPLICATION' : 'EXPLORE YOUR COLLECTION'} · ${selected.label || selected.id}</span>
          <h1>${systemName(selected)}</h1><p>${app ? 'Your favourites, on the big screen.' : 'Great adventures. All in one place.'}</p>
          <p className="orbit-muted">${app ? 'Installed application' : `${counts[selected.id] ?? 0} games in your library`}</p>
          <div className="orbit-actions"><button className="orbit-button orbit-primary" onClick=${() => onActivate(focusIdx)}>${app ? '▶ Open application' : 'Explore games'} <kbd>✕ / A</kbd></button>
            ${held ? html`<button className="orbit-button" onClick=${() => sessions.available() && sdk.session.resume(held.session).catch(() => {})}>Resume <kbd>L2</kbd></button>` : null}</div>
        </div><div className="orbit-feature-art"><${SystemArt} system=${selected} large=${true} /></div>
      </section>` : html`<section className="orbit-empty"><span className="orbit-eyebrow">MAKE YOURSELF AT HOME</span><h1>Your collection starts here.</h1><p>Install a console or application from Settings → Catalog.</p><p className="orbit-muted">Press Options / Menu to open Settings.</p></section>`}
      <${Footer} summary=${`${totals.systems} systems · ${totals.games} games · ${Math.round(totals.hours)} hours played`} />
    </main>`
  }
}
