import {createDetails} from './details.js'
import {createNavigation} from '../lib/navigation.js'
import {
  isApp, systemName, systemMark, accent, coverUrl,
  isFavourite, onFavouritesChange, favouriteCount,
} from '../lib/catalog.js'

const HEART = '<path d="M20.8 4.9a5.5 5.5 0 0 0-7.8 0L12 6l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.3a5.5 5.5 0 0 0 0-7.8Z"/>'
const SEARCH = '<circle cx="10.7" cy="10.7" r="6.7"/><path d="m16 16 4.5 4.5"/>'

/** Orbit's spatial library. The host owns loading, sorting, search, launching
 * and options; this view owns focus over the displayed grid and local favourites. */

/** Scroll the selection into view where the browser can, and shrug where it
 *  cannot. `scrollIntoView` is absent in jsdom and stubbed out by some
 *  accessibility tools; an unguarded call takes the whole screen down with it,
 *  which is a high price for a smooth scroll. */
const reveal = (el, opts) => {
  try { el?.scrollIntoView?.(opts) } catch { /* not worth a blank screen */ }
}

export function createLibrary(sdk, tabs, sessions, systemsRef, backdrop) {
  const {html, useState, useEffect, useRef, useMemo} = sdk.ui
  const Details = createDetails(sdk)
  const useNavigation = createNavigation(sdk)
  const svg = (d) => html`<svg viewBox="0 0 24 24" aria-hidden="true"
    dangerouslySetInnerHTML=${{__html: d}} />`

  function Cover({systemId, filename, title, favourite, held, onOpen, active, refFn, onSelect}) {
    const [failed, setFailed] = useState(false)
    const src = coverUrl(systemId, filename)
    return html`<button className=${`library-card ${active ? 'selected' : ''}`} ref=${refFn}
      data-active=${active ? 'true' : 'false'} aria-current=${active ? 'true' : undefined}
      onFocus=${onSelect} onClick=${onOpen}>
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
      onBack, onRetry, onSort, onOpenSearch, onOpenOptions} = props
    const [favouritesOnly, setFavouritesOnly] = useState(false)
    const [, bump] = useState(0)
    const grid = useRef(null)
    const root = useRef(null)
    const [details, setDetails] = useState(null)
    const screen = sdk.nav.use((s) => s.screen)
    const {background} = sdk.session.use()
    const machines = useMemo(
      () => (systemsRef.current || []).filter((s) => !isApp(s)), [systemsRef.current])

    useEffect(() => onFavouritesChange(() => bump((n) => n + 1)), [])
    useEffect(() => {tabs.rememberSystem(systemId)}, [systemId])

    const source = game => game?.system_id || systemId
    const identity = game => game ? `${source(game)}:${game.filename}` : ''
    const shown = useMemo(() => favouritesOnly
      ? games.filter((g) => isFavourite(source(g), g.filename))
      : games, [games, favouritesOnly, systemId, favouriteCount()])

    // The host's cursor indexes `games`; the favourites view is a subset, so the
    // highlight is matched by filename rather than by position. Filtering a list
    // the host is still counting through is exactly how an off-by-one highlight
    // gets shipped.
    const selectedFile = identity(games[selectedIdx])
    useEffect(() => {
      reveal(grid.current?.querySelector('[data-active="true"]'),
             {block: 'nearest', behavior: 'smooth'})
    }, [selectedFile, search, screen, favouritesOnly])

    const title = (g) => g?.display_name || (g ? sdk.format.gameName(g.filename) : '')
    const descriptor = game => ({systemId: source(game),
      system: machines.find(s => s.id === source(game)) || system, gameKey: game.filename, title: title(game)})
    const openGame = game => {
      onSelect(games.indexOf(game))
      setDetails(descriptor(game))
    }
    useEffect(() => {
      if (favouritesOnly && shown.length && !shown.some(g => identity(g) === selectedFile)) {
        onSelect(games.indexOf(shown[0]))
      }
    }, [shown, selectedFile, favouritesOnly])
    useEffect(() => {
      if (screen !== 'library') return
      backdrop?.select({kind: 'library', systemId: source(detailGame), filename: detailGame?.filename,
        accent: accent(sdk, system)})
    }, [screen, systemId, detailGame?.filename])
    useEffect(() => {
      const pending = tabs.pending?.()
      if (!pending || loading || loadError || system?.id !== systemId || screen !== 'library') return
      if (pending.systemId !== systemId) {tabs.clearLaunch(); return}
      const at = games.findIndex(g => g.filename === pending.gameKey)
      tabs.clearLaunch()
      if (at < 0) return
      onSelect(at)
      onLaunch()
    }, [screen, systemId, system, games, loading, loadError])
    const play = () => {
      const game = games[sdk.nav.get().selectedGameIdx]
      const held = game && sessions.heldMatch(background, game.filename, source(game))
      if (held) sdk.session.resume(held.session).catch(() => {})
      else onLaunch()
    }
    useNavigation(root, screen === 'library' && !loading && !launching, {
      confirm: () => {
        const game = shown.find(g => identity(g) === identity(games[sdk.nav.get().selectedGameIdx])) || shown[0]
        if (game) openGame(game)
      },
      tab: delta => tabs.step(delta, systemsRef.current),
      initial: '.library-card[data-active="true"]',
    })

    return html`<main className="orbit-main"><section id="library-view" className="collection-view" ref=${root}
                         style=${{'--console-accent': accent(sdk, system)}}
                         aria-labelledby="library-title">
      <div className="page-heading">
        <div><p className="eyebrow">ALL YOUR WORLDS, IN ONE PLACE</p>
          <h1 id="library-title">Your library.</h1></div>
        <span className="page-count">${shown.length} of ${totalCount} game${totalCount === 1 ? '' : 's'}</span>
      </div>

      <div className="library-toolbar">
        <div className="filters" aria-label="Choose a console">
          <button className=${`filter ${systemId === '__all__' ? 'active' : ''}`}
            aria-pressed=${String(systemId === '__all__')} onClick=${() => sdk.nav.goLibrary('__all__')}>All</button>
          ${machines.map((m) => html`<button key=${m.id}
            className=${`filter ${m.id === systemId ? 'active' : ''}`}
            aria-pressed=${String(m.id === systemId)}
            onClick=${() => sdk.nav.goLibrary(m.id)}>${systemMark(m)}</button>`)}
        </div>
        <label className="search-field">${svg(SEARCH)}
          <input value=${search} type="search" maxLength=${80}
                 placeholder="Search for a game…" aria-label="Search for a game"
                 onChange=${(e) => onSearch(e.target.value)} /></label>
        <button className="library-search-open" onClick=${onOpenSearch} aria-label="Open the search keyboard">
          ${svg(SEARCH)}<span>Search</span><kbd>△</kbd></button>
        <button className=${`filter-favorites ${favouritesOnly ? 'active' : ''}`}
                aria-pressed=${String(favouritesOnly)}
                onClick=${() => setFavouritesOnly((v) => !v)}>${svg(HEART)}Favourites</button>
        <div className="library-sort" aria-label="Sort games">
          ${sortKeys.map((key) => html`<button key=${key}
            data-active=${sort === key ? 'true' : 'false'} onClick=${() => onSort(key)}>${sortLabels[key]}</button>`)}
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
            ${shown.map((game) => html`<${Cover} key=${identity(game)}
              systemId=${source(game)} filename=${game.filename} title=${title(game)}
              favourite=${isFavourite(source(game), game.filename)}
              held=${!!sessions.heldMatch(background, game.filename, source(game))}
              active=${identity(game) === selectedFile}
              onSelect=${() => onSelect(games.indexOf(game))}
              onOpen=${() => openGame(game)} />`)}
          </div>`}

      ${details ? html`<${Details} game=${details} onClose=${() => setDetails(null)} onPlay=${play} />` : null}
      <div className="library-selection-actions">
        ${detailGame ? html`<button onClick=${onOpenOptions}>Game options <kbd>R2</kbd></button>` : null}
      </div>

    </section></main>`
  }
}
