import {
  isApp, systemName, systemMark, accent, coverUrl,
  isFavourite, toggleFavourite, onFavouritesChange, favouriteCount,
} from '../lib/catalog.js'

const HEART = '<path d="M20.8 4.9a5.5 5.5 0 0 0-7.8 0L12 6l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.3a5.5 5.5 0 0 0 0-7.8Z"/>'
const SEARCH = '<circle cx="10.7" cy="10.7" r="6.7"/><path d="m16 16 4.5 4.5"/>'

/** The library, as the mockup draws it, over the host's own library screen.
 *
 * Everything this screen DOES stays with `LibraryScreen`: the sort, the search
 * keyboard on △, the per-game options on R2, the launch and its ceremony, the
 * playtime. This file is markup — which is the contract (docs/themes/README.md
 * §5, "Views, not screens"), and also the only way the themed library behaves
 * exactly like the default one.
 *
 * Two things the mockup had that GameCore does not, and how they are met:
 *   · its filter chips listed every console and defaulted to "All". A box keeps
 *     its ROMs per console and the host's screen is scoped to one, so the chips
 *     SWITCH console — and "all of them" is the Consoles tab, which is a better
 *     answer than a chip anyway.
 *   · favourites are the theme's own, in this browser's storage. GameCore has
 *     no favourites: no endpoint, no column. The heart says so by being local.
 */

/** Scroll the selection into view where the browser can, and shrug where it
 *  cannot. `scrollIntoView` is absent in jsdom and stubbed out by some
 *  accessibility tools; an unguarded call takes the whole screen down with it,
 *  which is a high price for a smooth scroll. */
const reveal = (el, opts) => {
  try { el?.scrollIntoView?.(opts) } catch { /* not worth a blank screen */ }
}

export function createLibrary(sdk, tabs, sessions, systemsRef) {
  const {html, useState, useEffect, useRef, useMemo} = sdk.ui
  const svg = (d) => html`<svg viewBox="0 0 24 24" aria-hidden="true"
    dangerouslySetInnerHTML=${{__html: d}} />`

  function Cover({systemId, filename, title, favourite, held, onOpen, active, refFn}) {
    const [failed, setFailed] = useState(false)
    const src = coverUrl(systemId, filename)
    return html`<button className="library-card" ref=${refFn}
      data-active=${active ? 'true' : 'false'} aria-current=${active ? 'true' : undefined}
      onClick=${onOpen}>
      <span className="library-cover">
        ${!failed ? html`<img src=${src} alt="" loading="lazy" onError=${() => setFailed(true)} />`
          : html`<span className="art-fallback">${(title || '◇').slice(0, 2).toUpperCase()}</span>`}
        ${favourite ? html`<span className="cover-heart" aria-label="Favourite">${svg(HEART)}</span>` : null}
        ${held ? html`<span className="session-badge">IN BACKGROUND</span>` : null}
      </span>
      <h3>${title}</h3>
    </button>`
  }

  return function Library(props) {
    const {systemId, system, games, totalCount, selectedIdx, detailGame, sort, sortKeys,
      sortLabels, search, loading, loadError, launching, onSelect, onSearch, onLaunch,
      onBack, onRetry, Meta} = props
    const [favouritesOnly, setFavouritesOnly] = useState(false)
    const [, bump] = useState(0)
    const grid = useRef(null)
    const screen = sdk.nav.use((s) => s.screen)
    const {background} = sdk.session.use()
    const machines = useMemo(
      () => (systemsRef.current || []).filter((s) => !isApp(s)), [systemsRef.current])

    useEffect(() => onFavouritesChange(() => bump((n) => n + 1)), [])
    useEffect(() => {tabs.rememberSystem(systemId)}, [systemId])

    const shown = useMemo(() => favouritesOnly
      ? games.filter((g) => isFavourite(systemId, g.filename))
      : games, [games, favouritesOnly, systemId, favouriteCount()])

    // The host's cursor indexes `games`; the favourites view is a subset, so the
    // highlight is matched by filename rather than by position. Filtering a list
    // the host is still counting through is exactly how an off-by-one highlight
    // gets shipped.
    const selectedFile = games[selectedIdx]?.filename
    useEffect(() => {
      reveal(grid.current?.querySelector('[data-active="true"]'),
             {block: 'nearest', behavior: 'smooth'})
    }, [selectedFile, search, screen, favouritesOnly])

    const title = (g) => g?.display_name || (g ? sdk.format.gameName(g.filename) : '')
    const openGame = (game) => {
      const at = games.indexOf(game)
      if (at < 0) return
      if (at === selectedIdx) onLaunch()
      else onSelect(at)
    }

    return html`<section id="library-view" className="collection-view"
                         style=${{'--console-accent': accent(sdk, system)}}
                         aria-labelledby="library-title">
      <div className="page-heading">
        <div><p className="eyebrow">ALL YOUR WORLDS, IN ONE PLACE</p>
          <h1 id="library-title">${systemName(system)}</h1></div>
        <span className="page-count">${shown.length} of ${totalCount} game${totalCount === 1 ? '' : 's'}</span>
      </div>

      <div className="library-toolbar">
        <div className="filters" aria-label="Choose a console">
          ${machines.map((m) => html`<button key=${m.id}
            className=${`filter ${m.id === systemId ? 'active' : ''}`}
            aria-pressed=${String(m.id === systemId)}
            onClick=${() => sdk.nav.goLibrary(m.id)}>${systemMark(m)}</button>`)}
        </div>
        <label className="search-field">${svg(SEARCH)}
          <input value=${search} type="search" maxLength=${80}
                 placeholder="Search for a game…" aria-label="Search for a game"
                 onChange=${(e) => onSearch(e.target.value)} /></label>
        <button className="library-search-open" aria-label="Open the search keyboard">
          ${svg(SEARCH)}<span>Search</span><kbd>△</kbd></button>
        <button className=${`filter-favorites ${favouritesOnly ? 'active' : ''}`}
                aria-pressed=${String(favouritesOnly)}
                onClick=${() => setFavouritesOnly((v) => !v)}>${svg(HEART)}Favourites</button>
        <div className="library-sort" aria-label="Sort games">
          ${sortKeys.map((key) => html`<button key=${key}
            data-active=${sort === key ? 'true' : 'false'}>${sortLabels[key]}</button>`)}
        </div>
        <button className="icon-button" onClick=${onBack} aria-label="Back to consoles">←</button>
      </div>

      ${loadError ? html`<div className="empty-state"><h2>Could not load this library.</h2>
          <button className="primary-button" onClick=${onRetry}>Try again</button></div>`
        : loading ? html`<div className="empty-state" role="status"><h2>Opening your collection…</h2></div>`
        : !shown.length ? html`<div className="empty-state">
            <h2>${favouritesOnly ? 'No favourites here yet.' : search ? 'No games found' : 'Room for new adventures.'}</h2>
            <p>${favouritesOnly ? 'Mark a game with the heart to find it here.'
              : search ? 'Try another title, or clear the search with △.'
                : 'Add games to this console to see them here.'}</p>
            ${favouritesOnly ? html`<button className="primary-button"
              onClick=${() => setFavouritesOnly(false)}>Show every game</button>` : null}</div>`
        : html`<div className="library-grid" ref=${grid}>
            ${shown.map((game) => html`<${Cover} key=${game.filename}
              systemId=${systemId} filename=${game.filename} title=${title(game)}
              favourite=${isFavourite(systemId, game.filename)}
              held=${!!sessions.heldMatch(background, game.filename, systemId)}
              active=${game.filename === selectedFile}
              onOpen=${() => openGame(game)} />`)}
          </div>`}

      ${detailGame ? html`<div className="library-detail">
        <div className="library-detail-copy">
          <p className="eyebrow">${systemName(system)}</p>
          <h2>${title(detailGame)}</h2>
          <div className="orbit-meta"><${Meta} systemId=${systemId}
            filename=${detailGame.filename} extChip=${null}
            color=${accent(sdk, system)} /></div>
        </div>
        <div className="library-detail-actions">
          <button className="primary-button" disabled=${launching} onClick=${onLaunch}>
            ${launching ? 'Launching…' : '▶ Play'}<span className="button-key">✕</span></button>
          <button className=${`round-button favorite-button ${
            isFavourite(systemId, detailGame.filename) ? 'is-favourite' : ''}`}
            aria-pressed=${String(isFavourite(systemId, detailGame.filename))}
            aria-label="Favourite"
            onClick=${() => toggleFavourite(systemId, detailGame.filename)}>${svg(HEART)}</button>
        </div>
      </div>` : null}

      <div className="application-footer">
        <span><kbd>↑ ↓</kbd> Browse</span><span><kbd>✕</kbd> Play</span>
        <span><kbd>○</kbd> Back</span><span><kbd>△</kbd> Search</span>
        <span><kbd>L1 R1</kbd> Sort</span><span><kbd>R2</kbd> Options</span>
        <span className="session-footer-hint"><kbd>L2</kbd> Session</span>
      </div>
    </section>`
  }
}
