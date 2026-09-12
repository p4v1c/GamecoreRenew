import {createDetails} from './details.js'
import {createNavigation} from '../lib/navigation.js'
import {
  isApp, systemName, systemMark, accent,
  isFavourite, onFavouritesChange, favouriteCount,
} from '../lib/catalog.js'
import {createJacket} from '../lib/jacket.js'
import {reveal} from '../lib/dom.js'

const HEART = '<path d="M20.8 4.9a5.5 5.5 0 0 0-7.8 0L12 6l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.3a5.5 5.5 0 0 0 0-7.8Z"/>'
const SEARCH = '<circle cx="10.7" cy="10.7" r="6.7"/><path d="m16 16 4.5 4.5"/>'

/** Orbit's spatial library. The host owns loading, sorting, search, launching
 * and options; this view owns focus over the displayed grid and local favourites. */

export function createLibrary(sdk, tabs, sessions, systemsRef, backdrop) {
  const {html, useState, useEffect, useRef, useMemo} = sdk.ui
  const Details = createDetails(sdk)
  const Jacket = createJacket(sdk)
  const useNavigation = createNavigation(sdk)
  const svg = (d) => html`<svg viewBox="0 0 24 24" aria-hidden="true"
    dangerouslySetInnerHTML=${{__html: d}} />`

  function GameCard({systemId, filename, title, favourite, held, onOpen, active,
                     refFn, onSelect, onRatio}) {
    return html`<button className=${`library-card ${active ? 'selected' : ''}`} ref=${refFn}
      data-active=${active ? 'true' : 'false'} aria-current=${active ? 'true' : undefined}
      onFocus=${onSelect} onClick=${onOpen}>
      <span className="library-cover">
        <${Jacket} key=${`${systemId}:${filename}`} className="library-jacket"
          systemId=${systemId} filename=${filename} title=${title} onRatio=${onRatio} />
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
    // The shape of the SHELF, measured once per console.
    //
    // Every cell reserved a 2:3 portrait, which is right for a Switch case and
    // wrong for everything else: a Game Boy box is nearly square and a
    // Nintendo 64 carton is landscape, so each row carried a band of empty
    // space as tall as the difference. 3.6.19 made the frame hug the artwork,
    // which fixed the border and left the band.
    //
    // Letting each card size itself is the thing the fixed cell was protecting
    // against — "changing every card's grid geometry as hundreds of cached
    // images decode stalls pad navigation on larger libraries". But a console's
    // boxes are all the same shape, and a library view is one console, so ONE
    // ratio describes the whole grid: the wall relayouts once, when the first
    // jacket decodes, and never again.
    //
    // The ref is what makes it once. State alone would take whichever picture
    // decoded last and move the wall under the player's thumb every time a
    // scraped cover arrived a few pixels off its neighbour.
    const shelf = useRef(null)
    const [shelfRatio, setShelfRatio] = useState(null)
    const root = useRef(null)
    const [details, setDetails] = useState(null)
    const [summary, setSummary] = useState(null)
    const screen = sdk.nav.use((s) => s.screen)
    const {background} = sdk.session.use()
    const machines = useMemo(
      () => (systemsRef.current || []).filter((s) => !isApp(s)), [systemsRef.current])

    useEffect(() => onFavouritesChange(() => bump((n) => n + 1)), [])
    useEffect(() => {tabs.rememberSystem(systemId)}, [systemId])
    useEffect(() => {shelf.current = null; setShelfRatio(null)}, [systemId])
    const noteShelf = ratio => {
      if (shelf.current !== null) return
      shelf.current = ratio
      setShelfRatio(ratio)
    }

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

    useEffect(() => {
      let live = true
      setSummary(null)
      if (!detailGame) return
      const timer = setTimeout(() => {
        sdk.api.metadata.get(source(detailGame), detailGame.filename)
          .then(meta => { if (live && meta?.found) setSummary(meta) }).catch(() => {})
      }, 180)
      return () => { live = false; clearTimeout(timer) }
    }, [detailGame?.filename, detailGame?.system_id, systemId])

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
        <div><button className="filter" onClick=${() => tabs.go('systems', systemsRef.current)}
          aria-label="Back to consoles">← Consoles</button>
          <p className="eyebrow">YOUR CONSOLE COLLECTION</p>
          <h1 id="library-title">${systemId === '__all__' ? 'All games.' : (system?.label || 'Your library.')}</h1></div>
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

      ${detailGame && !loading ? html`<div className="orbit-library-summary">
        <div><strong>${title(detailGame)}</strong><span>${systemName(machines.find(m => m.id === source(detailGame)) || system)}${summary?.year ? ` · ${summary.year}` : ''}</span></div>
        <p>${summary?.description || 'Open details to explore this game.'}</p>
      </div>` : null}
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
        : html`<div className="library-grid" ref=${grid}
                    style=${shelfRatio ? {'--jacket-ratio': String(shelfRatio)} : null}>
            ${shown.map((game) => html`<${GameCard} key=${identity(game)}
              systemId=${source(game)} filename=${game.filename} title=${title(game)}
              favourite=${isFavourite(source(game), game.filename)}
              held=${!!sessions.heldMatch(background, game.filename, source(game))}
              active=${identity(game) === selectedFile}
              onSelect=${() => onSelect(games.indexOf(game))}
              onOpen=${() => openGame(game)}
              onRatio=${systemId === '__all__' ? null : noteShelf} />`)}
          </div>`}

      ${details ? html`<${Details} game=${details} onClose=${() => setDetails(null)} onPlay=${play} />` : null}
      <div className="library-selection-actions">
        ${detailGame ? html`<button onClick=${onOpenOptions}>Game options <kbd>R2</kbd></button>` : null}
      </div>

    </section></main>`
  }
}
