import {
  isApp, systemName, systemMark, systemMaker, systemYear, systemStory,
  appStyle, accent, packLogo, coverUrl, consoleArt,
  isFavourite, toggleFavourite, onFavouritesChange, titleFromKey,
} from '../lib/catalog.js'

const ICON = {
  play: '<path d="m7 4 14 8-14 8z"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  heart: '<path d="M20.8 4.9a5.5 5.5 0 0 0-7.8 0L12 6l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.3a5.5 5.5 0 0 0 0-7.8Z"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
}


/** Scroll the selection into view where the browser can, and shrug where it
 *  cannot. `scrollIntoView` is absent in jsdom and stubbed out by some
 *  accessibility tools; an unguarded call takes the whole screen down with it,
 *  which is a high price for a smooth scroll. */
const reveal = (el, opts) => {
  try { el?.scrollIntoView?.(opts) } catch { /* not worth a blank screen */ }
}

export function createHome(sdk, tabs, sessions, systemsRef) {
  const {html, useState, useEffect, useRef, useMemo} = sdk.ui
  const svg = (name) => html`<svg viewBox="0 0 24 24" aria-hidden="true"
    dangerouslySetInnerHTML=${{__html: ICON[name]}} />`

  /** Recently played, across every console.
   *
   * The mockup's rail listed twelve invented games. A real box has however many
   * ROMs the owner put on it — thousands, on the reference box — so "every
   * game" is not a rail, it is a scrolling wall nobody reaches the end of. What
   * the playtime table already knows is the useful subset: what was played, and
   * when. So the rail is a continue-playing rail, and the whole library is one
   * tile away at the end of it.
   */
  function useRecent(systems) {
    const [rows, setRows] = useState([])
    useEffect(() => {
      let live = true
      sdk.api.playtime.all()
        .then((entries) => {
          if (!live || !Array.isArray(entries)) return
          const known = new Map(systems.map((s) => [s.id, s]))
          setRows(entries
            .filter((e) => known.has(e.system_id) && !isApp(known.get(e.system_id)))
            .sort((a, b) => String(b.last_played || '').localeCompare(String(a.last_played || '')))
            .slice(0, 18)
            .map((e) => ({
              key: `${e.system_id}:${e.game_key}`,
              gameKey: e.game_key, systemId: e.system_id,
              system: known.get(e.system_id),
              title: titleFromKey(sdk, e.game_key),
              seconds: e.total_secs, lastPlayed: e.last_played,
            })))
        })
        .catch(() => { /* an empty rail is the honest answer */ })
      return () => {live = false}
    }, [systems])
    return rows
  }

  /** The metadata panel of the hero, for whichever game is selected. */
  function useGameMeta(item) {
    const [meta, setMeta] = useState(null)
    useEffect(() => {
      setMeta(null)
      if (!item) return
      let live = true
      sdk.api.metadata.get(item.systemId, item.gameKey)
        .then((m) => {if (live && m?.found) setMeta(m)})
        .catch(() => { /* no metadata is a shorter hero, not an error */ })
      return () => {live = false}
    }, [item?.key])
    return meta
  }

  function useFavourites() {
    const [, bump] = useState(0)
    useEffect(() => onFavouritesChange(() => bump((n) => n + 1)), [])
  }

  // ── the Games tab ─────────────────────────────────────────────────────────

  function GamesTab({systems, counts, totals}) {
    const recent = useRecent(systems)
    const apps = useMemo(() => systems.filter(isApp), [systems])
    const [idx, setIdx] = useState(0)
    const rail = useRef(null)
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
      reveal(rail.current?.querySelector('[data-active="true"]'),
             {block: 'nearest', inline: 'center', behavior: 'smooth'})
    }, [at])

    // The host's d-pad is omitted on this screen (homeOmit), so the rail binds
    // its own — see index.js for why, and what it costs.
    const move = (delta) => setIdx((i) =>
      (i + delta + items.length) % Math.max(1, items.length))
    const open = () => {
      if (!item) return
      if (item.kind === 'collection') {tabs.go('library', systems); return}
      if (item.kind === 'app') {sdk.defaults.launchApp(item.system); return}
      const held = sessions.heldMatch(background, item.gameKey, item.systemId)
      if (held) {sdk.session.resume(held.session).catch(() => {}); return}
      // The rail knows the key, not the path; the library screen is what holds
      // the scan. Opening it there is also what gives the player the sort, the
      // per-game options and the launch ceremony they get everywhere else.
      tabs.rememberSystem(item.systemId)
      sdk.nav.goLibrary(item.systemId)
    }
    useHomeKeys(move, open, 'home')

    const art = item?.kind === 'game'
      ? coverUrl(item.systemId, item.gameKey)
      : item?.kind === 'app' ? packLogo(item.system) : null
    const tint = item?.kind === 'app' ? appStyle(item.system).color
      : item?.kind === 'game' ? accent(sdk, item.system) : '#8dc0f5'

    return html`<section id="home-view" aria-label="Games home">
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
            return html`<button key=${it.key} className="game-tile home-collection-tile"
              data-active=${on ? 'true' : 'false'} aria-pressed=${String(on)}
              aria-label="Open the library" onClick=${() => {setIdx(i); tabs.go('library', systems)}}>
              <span className="tile-art">${svg('grid')}</span><span className="tile-label">Collection</span></button>`
          }
          if (it.kind === 'app') {
            const style = appStyle(it.system)
            return html`<button key=${it.key} className="game-tile home-app-tile"
              data-active=${on ? 'true' : 'false'} aria-pressed=${String(on)}
              style=${{'--home-tile-accent': style.color, '--app-tile-color': style.tile,
                       '--app-logo-scale': style.scale}}
              aria-label=${`Select ${systemName(it.system)}`}
              onClick=${() => setIdx(i)}>
              <span className="tile-art"><${Art} src=${packLogo(it.system)} alt=${systemName(it.system)} />
                ${sessions.heldMatch(background, it.system.id, it.system.id)
                  ? html`<span className="session-badge">IN BACKGROUND</span>` : null}</span>
              <span className="tile-label">${systemName(it.system)}</span></button>`
          }
          return html`<button key=${it.key} className="game-tile"
            data-active=${on ? 'true' : 'false'} aria-pressed=${String(on)}
            aria-label=${`Select ${it.title}`} onClick=${() => setIdx(i)}>
            <span className="tile-art"><${Art} src=${coverUrl(it.systemId, it.gameKey)} alt=${it.title} />
              ${sessions.heldMatch(background, it.gameKey, it.systemId)
                ? html`<span className="session-badge">IN BACKGROUND</span>` : null}</span>
            <span className="tile-label">${it.title}</span></button>`
        })}
      </div>
      ${item ? html`<${Hero} item=${item} meta=${meta} art=${art} tint=${tint}
                             counts=${counts} totals=${totals} onOpen=${open} />`
        : html`<div className="hero"><div className="hero-copy">
            <div className="eyebrow"><span className="platform">GAMES</span><span>Nothing played yet</span></div>
            <h1>Your collection starts here.</h1>
            <p>Add a console from Settings → Catalog, then open it to see your games.</p>
          </div></div>`}
    </section>`
  }

  function Hero({item, meta, art, tint, counts, totals, onOpen}) {
    const {background} = sdk.session.use()
    if (item.kind === 'collection') {
      return html`<div className="hero" style=${{'--home-service-accent': tint}}>
        <div className="hero-copy">
          <div className="eyebrow"><span className="platform">GAMES</span><span>Your collection</span>
            <span className="dot" /><span>${totals.games} games</span></div>
          <h1 className="home-app-title">Your library.</h1>
          <p>Find all your games, consoles, and favourites.</p>
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
          <h1 className="home-app-title">${systemName(item.system)}</h1>
          <p>${s.description}</p>
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
        <h1>${meta?.title || item.title}</h1>
        <p>${meta?.description
          ? meta.description.split(/(?<=\.)\s+/).slice(0, 2).join(' ')
          : `${sdk.format.time(item.seconds)} played · last ${sdk.format.date(item.lastPlayed)}`}</p>
        <div className="game-meta">
          ${meta?.genres?.length ? html`<span>${meta.genres.slice(0, 2).join(' · ')}</span><span className="dot" />` : null}
          ${meta?.year ? html`<span>${meta.year}</span><span className="dot" />` : null}
          <span>${sdk.format.time(item.seconds)} played</span>
        </div>
        <div className="hero-actions">
          <button className="primary-button" onClick=${onOpen}>${svg('play')}${
            held ? 'Resume' : 'Play'}<span className="button-key">✕</span></button>
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

  // ── the Consoles tab ──────────────────────────────────────────────────────

  function ConsolesTab({systems, counts}) {
    const machines = useMemo(() => systems.filter((s) => !isApp(s)), [systems])
    const [idx, setIdx] = useState(0)
    const grid = useRef(null)
    const at = Math.min(idx, Math.max(0, machines.length - 1))
    const s = machines[at]

    useEffect(() => {
      reveal(grid.current?.querySelector('[data-active="true"]'),
             {block: 'nearest', inline: 'center', behavior: 'smooth'})
    }, [at])

    const move = (d) => setIdx((i) => (i + d + machines.length) % Math.max(1, machines.length))
    const open = () => {
      if (!s) return
      tabs.rememberSystem(s.id)
      sdk.nav.goLibrary(s.id)
    }
    useHomeKeys(move, open, 'systems')

    if (!machines.length) {
      return html`<section id="systems-view" className="collection-view consoles-view">
        <div className="page-heading"><div><p className="eyebrow">YOUR CONSOLE COLLECTION</p>
          <h1>No consoles yet.<br /><span>Add one to begin.</span></h1></div></div>
        <p className="mock-footnote">Settings → Catalog installs an emulator.</p></section>`
    }
    return html`<section id="systems-view" className="collection-view consoles-view"
                         aria-labelledby="systems-title">
      <div className="page-heading">
        <div><p className="eyebrow">YOUR CONSOLE COLLECTION</p>
          <h1 id="systems-title">Every generation.<br /><span>One place.</span></h1></div>
        <div className="console-summary"><strong>${machines.length}</strong>
          <span>console${machines.length === 1 ? '' : 's'} & handhelds</span></div>
      </div>
      <div className="console-showcase" style=${{'--console-accent': accent(sdk, s)}}>
        <div className="console-story">
          <div className="console-kicker"><span className="console-maker">${(systemMaker(s) || 'GAMECORE').toUpperCase()}</span>
            <span>${systemYear(s)}</span><span className="dot" /><span>CONSOLE</span></div>
          <h2>${systemName(s)}</h2>
          <p>${systemStory(s)}</p>
          <div className="console-facts"><span>${counts[s.id] ?? 0} game${(counts[s.id] ?? 0) === 1 ? '' : 's'}</span>
            <span className="dot" /><span>${s.label || s.id}</span></div>
          <button className="primary-button" onClick=${open}>${svg('grid')}Browse games<span>✕</span></button>
        </div>
        <div className="console-exhibit"><span className="console-halo" /><span className="console-plinth" />
          <${Art} className="console-photo" src=${consoleArt(sdk, s)} alt=${systemName(s)} />
          <span className="exhibit-number">${String(at + 1).padStart(2, '0')}<small> / ${machines.length}</small></span>
        </div>
      </div>
      <div className="section-heading machines-heading"><h2>Choose a console</h2><span>← → to browse</span></div>
      <div className="systems-grid" ref=${grid}>
        ${machines.map((m, i) => html`<button key=${m.id}
          className=${`machine-tile ${i === at ? 'selected' : ''}`}
          data-active=${i === at ? 'true' : 'false'} aria-pressed=${String(i === at)}
          aria-label=${`View ${systemName(m)}`}
          onClick=${() => (i === at ? open() : setIdx(i))}>
          <span className="machine-image"><${Art} src=${consoleArt(sdk, m)} alt="" /></span>
          <span>${systemMark(m)}</span><small>${systemMaker(m) || (m.label || m.id)}</small>
        </button>`)}
      </div>
    </section>`
  }

  // ── the Applications tab ──────────────────────────────────────────────────

  function ApplicationsTab({systems}) {
    const apps = useMemo(() => systems.filter(isApp), [systems])
    const [idx, setIdx] = useState(0)
    const {background} = sdk.session.use()
    const at = Math.min(idx, Math.max(0, apps.length - 1))
    const app = apps[at]
    const move = (d) => setIdx((i) => (i + d + apps.length) % Math.max(1, apps.length))
    const open = () => {
      if (!app) return
      const held = sessions.heldMatch(background, app.id, app.id)
      if (held) {sdk.session.resume(held.session).catch(() => {}); return}
      sdk.defaults.launchApp(app)
    }
    useHomeKeys(move, open, 'applications')

    if (!app) {
      return html`<section id="applications-view" className="collection-view applications-view">
        <div className="page-heading"><div><p className="eyebrow">YOUR LIVING ROOM. EVERY WORLD.</p>
          <h1>No applications yet.</h1></div></div>
        <p className="mock-footnote">Settings → Catalog installs Steam, YouTube, Twitch and Stremio.</p></section>`
    }
    const s = appStyle(app)
    const held = sessions.heldMatch(background, app.id, app.id)
    return html`<section id="applications-view" className="collection-view applications-view"
                         style=${{'--application-accent': s.color}} aria-labelledby="applications-title">
      <div className="page-heading"><div><p className="eyebrow">YOUR LIVING ROOM. EVERY WORLD.</p>
        <h1 id="applications-title">Your apps.</h1></div>
        <span className="page-count">${apps.length} pack${apps.length === 1 ? '' : 's'}</span></div>
      <div className="application-rail" aria-label="Choose an app">
        ${apps.map((a, i) => {
          const st = appStyle(a)
          return html`<button key=${a.id}
            className=${`application-tile ${i === at ? 'selected' : ''}`}
            data-active=${i === at ? 'true' : 'false'} aria-pressed=${String(i === at)}
            style=${{'--tile-color': st.color, '--app-tile-color': st.tile, '--app-logo-scale': st.scale}}
            aria-label=${`Select ${systemName(a)}`}
            onClick=${() => (i === at ? open() : setIdx(i))}>
            <span className="application-tile-image"><${Art} src=${packLogo(a)} alt="" />
              ${sessions.heldMatch(background, a.id, a.id)
                ? html`<span className="session-badge">IN BACKGROUND</span>` : null}</span>
            <span className="application-tile-title">${systemName(a)}</span><small>${st.category}</small>
          </button>`
        })}
      </div>
      <div className="application-feature">
        <div className="application-copy">
          <p className="eyebrow"><span className="application-category">${s.category}</span>
            <span className="dot" />${s.edition}</p>
          <h2>${systemName(app)}</h2>
          <p className="application-description">${s.description}</p>
          <button className="primary-button" onClick=${open}>${svg('play')}${
            held ? 'Resume' : 'Open'} ${systemName(app)}<span className="application-confirm">✕</span></button>
          <span className="application-pack">GameCore pack · ${app.id}</span>
        </div>
        <div className="application-emblem" aria-hidden="true">
          <div className="application-emblem-orbit" />
          <div className="application-emblem-tile"
               style=${{'--app-tile-color': s.tile, '--app-logo-scale': s.scale}}>
            <${Art} src=${packLogo(app)} alt="" /></div>
          <span>${s.edition}</span>
        </div>
      </div>
      <div className="application-footer">
        <span><kbd>L1</kbd><kbd>R1</kbd> Switch tabs</span><span><kbd>← →</kbd> Choose</span>
        <span><kbd>✕</kbd> Open</span><span><kbd>□</kbd> Inputs</span>
        <span className="session-footer-hint"><kbd>L2</kbd> Session</span>
      </div>
    </section>`
  }

  /** One binding set for whichever home tab is on screen.
   *
   * The host's own d-pad, L1/R1 and ✕ are dropped for this screen (`homeOmit`
   * in index.js), so these are not competing with anything — which is the whole
   * reason for dropping them. Registered once and reading the live tab, so a
   * tab change does not tear listeners down and rebuild them.
   */
  function useHomeKeys(move, open, owns) {
    const live = useRef({move, open, owns})
    live.current = {move, open, owns}
    useEffect(() => {
      const mine = () => {
        const s = sdk.nav.get()
        return s.screen === 'home' && !s.modalDepth && !s.sessionGameKey
          && !s.powerPending && s.standby === 'off' && tabs.get() === live.current.owns
      }
      const offs = [
        sdk.input.onGp('gp:dpad-left', () => {if (mine()) live.current.move(-1)}),
        sdk.input.onGp('gp:dpad-right', () => {if (mine()) live.current.move(1)}),
        sdk.input.onGp('gp:dpad-up', () => {if (mine()) live.current.move(-1)}),
        sdk.input.onGp('gp:dpad-down', () => {if (mine()) live.current.move(1)}),
        sdk.input.onGp('gp:confirm', () => {if (mine()) live.current.open()}),
        sdk.input.onGp('gp:l1', () => {if (mine()) tabs.step(-1, systemsRef.current)}),
        sdk.input.onGp('gp:r1', () => {if (mine()) tabs.step(1, systemsRef.current)}),
      ]
      return () => offs.forEach((off) => off())
    }, [])
  }

  /** An image that falls back to initials rather than a broken frame. */
  function Art({src, alt = '', className = ''}) {
    const [failed, setFailed] = useState(false)
    return src && !failed
      ? html`<img className=${className} src=${src} alt=${alt} draggable="false"
                  onError=${() => setFailed(true)} />`
      : html`<span className="art-fallback">${(alt || '◇').slice(0, 2).toUpperCase()}</span>`
  }

  return function Home(props) {
    const tab = tabs.useTab()
    systemsRef.current = props.systems
    if (tab === 'systems') return html`<${ConsolesTab} ...${props} />`
    if (tab === 'applications') return html`<${ApplicationsTab} ...${props} />`
    return html`<${GamesTab} ...${props} />`
  }
}
