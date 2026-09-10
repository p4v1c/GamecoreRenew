import {
  isApp, systemName, systemMark, appStyle, accent, packLogo,
  isFavourite, toggleFavourite,
} from '../../lib/catalog.js'
import {reveal} from '../../lib/dom.js'

export function createGamesTab({sdk, tabs, sessions, backdrop, Details, Jacket, Art, svg, hooks}) {
  const {html, useState, useEffect, useRef, useMemo} = sdk.ui
  const {useRecent, useGameMeta, useFavourites, useHomeKeys} = hooks

  // ── the Games tab ─────────────────────────────────────────────────────────

  function GamesTab({systems, counts, totals}) {
    const recent = useRecent(systems)
    const apps = useMemo(() => systems.filter(isApp), [systems])
    const [idx, setIdx] = useState(0)
    const rail = useRef(null)
    const [showDetails, setShowDetails] = useState(false)
    const [launchError, setLaunchError] = useState('')
    const screen = sdk.nav.use(s => s.screen)
    useFavourites()
    const {background} = sdk.session.use()

    /** Games, applications and the way into the whole library — the mockup's
     *  mixed rail, built from what this box actually has. */
    const items = useMemo(() => {
      const out = []
      let app = 0
      recent.forEach((game, i) => {
        out.push({kind: 'game', ...game})
        if (i % 2 === 0 && app < apps.length) {
          const s = apps[app++]
          out.push({kind: 'app', key: `app:${s.id}`, system: s})
        }
      })
      while (app < apps.length) {
        const s = apps[app++]
        out.push({kind: 'app', key: `app:${s.id}`, system: s})
      }
      out.push({kind: 'collection', key: 'collection'})
      return out
    }, [recent, apps])

    const at = Math.min(idx, Math.max(0, items.length - 1))
    const item = items[at]
    const meta = useGameMeta(item?.kind === 'game' ? item : null)
    useEffect(() => {
      if (screen !== 'home' || tabs.get() !== 'home') return
      backdrop?.select({kind: item?.kind, systemId: item?.systemId, filename: item?.gameKey,
        accent: item?.system ? accent(sdk, item.system) : '#8dc0f5'})
    }, [item?.key, screen])

    useEffect(() => {
      reveal(rail.current?.querySelector('[data-active="true"]'),
             {block: 'nearest', inline: 'center', behavior: 'smooth'})
    }, [at])

    // The host's d-pad is omitted on this screen (homeOmit), so the rail binds
    // its own — see index.js for why, and what it costs.
    const move = (delta) => setIdx((i) =>
      (i + delta + items.length) % Math.max(1, items.length))
    const open = () => {
      if (!item) return
      if (item.kind === 'collection') {tabs.go('systems', systems); return}
      if (item.kind === 'app') {
        const held = sessions.heldMatch(background, item.system.id, item.system.id)
        if (held) sdk.session.resume(held.session).catch(() => {})
        else sdk.defaults.launchApp(item.system)
        return
      }
      const held = sessions.heldMatch(background, item.gameKey, item.systemId)
      if (held) {sdk.session.resume(held.session).catch(() => {}); return}
      setShowDetails(false)
      setLaunchError('')
      sdk.defaults.launchGame(item).catch(error => setLaunchError(error.message || 'Could not launch game'))
    }
    useHomeKeys(move, open, 'home')

    const tint = item?.kind === 'app' ? appStyle(item.system).color
      : item?.kind === 'game' ? accent(sdk, item.system) : '#8dc0f5'

    return html`<section id="home-view" aria-label="Games home">
      ${launchError ? html`<p role="alert">${launchError}</p>` : null}
      <div className="rail-heading"><span>GAMES & APPS</span>
        <div className="home-rail-controls">
          <span id="rail-counter">${String(at + 1).padStart(2, '0')} <i>/ ${String(items.length).padStart(2, '0')}</i></span>
          <button onClick=${() => move(-1)} aria-label="Previous item">←</button>
          <button onClick=${() => move(1)} aria-label="Next item">→</button>
        </div>
      </div>
      <div className="game-rail" ref=${rail} aria-label="Game and app selection">
        ${items.map((it, i) => {
          const on = i === at
          if (it.kind === 'collection') {
            return html`<button key=${it.key} className=${`game-tile home-collection-tile ${on ? 'selected' : ''}`}
              data-active=${on ? 'true' : 'false'} aria-pressed=${String(on)}
              aria-label="Open the library" onClick=${() => {setIdx(i); tabs.go('systems', systems)}}>
              <span className="tile-art">${svg('grid')}</span><span className="tile-label">Collection</span></button>`
          }
          if (it.kind === 'app') {
            const style = appStyle(it.system)
            return html`<button key=${it.key} className=${`game-tile home-app-tile ${on ? 'selected' : ''}`}
              data-active=${on ? 'true' : 'false'} aria-pressed=${String(on)}
              style=${{'--home-tile-accent': style.color, '--app-tile-color': style.tile,
                       '--app-logo-scale': style.scale}}
              aria-label=${`Select ${systemName(it.system)}`}
              onFocus=${() => setIdx(i)} onClick=${() => setIdx(i)}>
              <span className="tile-art"><${Art} src=${packLogo(it.system)} alt=${systemName(it.system)} />
                ${sessions.heldMatch(background, it.system.id, it.system.id)
                  ? html`<span className="session-badge">IN BACKGROUND</span>` : null}</span>
              <span className="tile-label">${systemName(it.system)}</span></button>`
          }
          return html`<button key=${it.key} className=${`game-tile home-game-tile ${on ? 'selected' : ''}`}
            data-active=${on ? 'true' : 'false'} aria-pressed=${String(on)}
            aria-label=${`Select ${it.title}`} onFocus=${() => setIdx(i)} onClick=${() => setIdx(i)}>
            <span className="tile-art"><${Jacket} key=${it.key} className="home-game-cover"
              systemId=${it.systemId} filename=${it.gameKey} title=${it.title} />
              ${sessions.heldMatch(background, it.gameKey, it.systemId)
                ? html`<span className="session-badge">IN BACKGROUND</span>` : null}</span>
            <span className="tile-label" title=${it.title}>${it.title}</span></button>`
        })}
      </div>
      ${item ? html`<${Hero} item=${item} meta=${meta} tint=${tint}
                             counts=${counts} totals=${totals} onOpen=${open} onDetails=${() => setShowDetails(true)} />`
        : html`<div className="hero"><div className="hero-copy">
            <div className="eyebrow"><span className="platform">GAMES</span><span>Nothing played yet</span></div>
            <h1>Your collection starts here.</h1>
            <p>Add a console from Settings → Catalog, then open it to see your games.</p>
          </div></div>`}
      ${showDetails && item?.kind === 'game' ? html`<${Details} game=${item} onClose=${() => setShowDetails(false)} onPlay=${open} />` : null}
    </section>`
  }

  function Hero({item, meta, tint, totals, onOpen, onDetails}) {
    const {background} = sdk.session.use()
    if (item.kind === 'collection') {
      return html`<div className="hero" style=${{'--home-service-accent': tint}}>
        <div className="hero-copy">
          <div className="eyebrow"><span className="platform">GAMES</span><span>Your collection</span>
            <span className="dot" /><span>${totals.games} games</span></div>
          <h1 id="hero-title" className="home-app-title">Your library.</h1>
          <p id="hero-description">Find all your games, consoles, and favourites.</p>
          <div className="hero-actions">
            <button className="primary-button" onClick=${onOpen}>${svg('grid')}Browse library<span className="button-key">✕</span></button>
          </div>
        </div>
        <div className="home-service-art"><div className="home-service-orbit" />${svg('grid')}<span>YOUR ENTIRE COLLECTION</span></div>
      </div>`
    }
    if (item.kind === 'app') {
      const s = appStyle(item.system)
      const held = sessions.heldMatch(background, item.system.id, item.system.id)
      return html`<div className="hero" style=${{'--home-service-accent': s.color}}>
        <div className="hero-copy">
          <div className="eyebrow"><span className="platform">APP</span><span>${s.category}</span>
            <span className="dot" /><span>${s.edition}</span></div>
          <h1 id="hero-title" className="home-app-title">${systemName(item.system)}</h1>
          <p id="hero-description">${s.description}</p>
          <div className="hero-actions">
            <button className="primary-button" onClick=${onOpen}>${svg('play')}${
              held ? 'Resume' : 'Open'} ${systemName(item.system)}<span className="button-key">✕</span></button>
          </div>
        </div>
        <div className="home-service-art"><div className="home-service-orbit" />
          <${Art} src=${packLogo(item.system)} alt=${systemName(item.system)} /><span>${s.edition}</span></div>
      </div>`
    }
    const held = sessions.heldMatch(background, item.gameKey, item.systemId)
    const fav = isFavourite(item.systemId, item.gameKey)
    return html`<div className="hero" key=${item.key}>
      <div className="hero-copy">
        <div className="eyebrow">
          <span className="platform">${systemMark(item.system)}</span>
          <span>${systemName(item.system)}</span><span className="dot" />
          <span>${item.system?.label || item.systemId}</span>
        </div>
        <h1 id="hero-title">${meta?.title || item.title}</h1>
        <p id="hero-description">${meta?.description
          ? meta.description.split(/(?<=\.)\s+/).slice(0, 2).join(' ')
          : item.lastPlayed ? `${sdk.format.time(item.seconds)} played · last ${sdk.format.date(item.lastPlayed)}` : 'Ready for your next adventure.'}</p>
        <div className="game-meta">
          ${Array.isArray(meta?.genres) && meta.genres.length ? html`<span className="orbit-meta-group"><span>${meta.genres.slice(0, 2).join(' · ')}</span><span className="dot" /></span>` : null}
          ${meta?.year ? html`<span className="orbit-meta-group"><span>${meta.year}</span><span className="dot" /></span>` : null}
          <span>${sdk.format.time(item.seconds)} played</span>
        </div>
        <div className="hero-actions">
          <button className="primary-button" onClick=${onOpen}>${svg('play')}${
            held ? 'Resume' : 'Play'}<span className="button-key">✕</span></button>
          <button className="round-button" aria-label="Game details" onClick=${onDetails}>${svg('more')}</button>
          <button className=${`round-button favorite-button ${fav ? 'is-favourite' : ''}`}
                  aria-pressed=${String(fav)}
                  aria-label=${fav ? 'Remove from favourites' : 'Add to favourites'}
                  onClick=${() => toggleFavourite(item.systemId, item.gameKey)}>${svg('heart')}</button>
        </div>
      </div>
      <div className="hero-aside"><span className="aside-line" />
        <p>THE JOY OF<br /><strong>picking up where you left off.</strong></p>
        <span className="edition">YOUR COLLECTION. YOUR ADVENTURES.</span></div>
    </div>`
  }

  return GamesTab
}
