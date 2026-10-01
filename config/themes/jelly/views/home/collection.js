import {isApp, systemMark, systemName, plural} from '../../lib/catalog.js'
import {favouriteCount, createUseFavourites} from '../../lib/favourites.js'
import {createSpatial} from '../../lib/spatial.js'
import {homeOwnsPad} from '../../lib/presses.js'
import {searchGames} from '../../lib/search.js'
import {heldSession} from '../../lib/launch.js'

// Cards drawn at once; the grid grows as the cursor nears its end.
const PAGE = 40
const GROW_BEFORE_END = 10

/** Collection: every game, filtered by console or favourites. */
export function createCollectionTab(sdk, {tabs, cards, chips, Icon, Footer, hints}) {
  const {html, useState, useEffect, useRef, useMemo} = sdk.ui
  const {Fragment} = sdk.ui.React
  const useSpatial = createSpatial(sdk)
  const useFavourites = createUseFavourites(sdk)
  // Kept across tab switches, so coming back finds the same filter.
  let lastFilter = 'all'

  function Body({data, shown, filter, limit, background, onRetry, onShowAll, onDetails}) {
    if (data.status === 'error') {
      return html`<div className="jl-empty"><b>The collection isn’t answering.</b>
        <p>No console sent its game list.</p>
        <button type="button" className="jl-play" data-nav="retry" onClick=${onRetry}>Try again</button></div>`
    }
    if ((data.status === 'loading' || data.status === 'idle') && !data.games.length) {
      return html`<div className="jl-empty" role="status"><b>Opening the game box.</b></div>`
    }
    if (!shown.length) {
      return html`<div className="jl-empty">
        <b>${filter === 'fav' ? 'No favourites yet.' : 'Nothing here yet.'}</b>
        <p>${filter === 'fav' ? 'Open a game’s details and press △ to add it.'
          : 'Add games to your consoles to see them here.'}</p>
        ${filter !== 'all' ? html`<button type="button" className="jl-play" data-nav="show-all" onClick=${onShowAll}>Show all games</button>` : null}</div>`
    }
    return html`<${Fragment}><div className="jl-grid">
        ${shown.slice(0, limit).map((g, i) => html`<${cards.GameCard} key=${g.key} game=${g} nav=${`g-${g.key}`}
          index=${i} held=${!!heldSession(background, g)} onPress=${() => onDetails(g)} />`)}
      </div>
      ${shown.length > limit ? html`<p className="jl-more">${plural(shown.length - limit, 'more game', 'more games')} below</p>` : null}<//>`
  }

  return function CollectionTab({data, systems, actions, onDetails, onSearch}) {
    const root = useRef(null)
    const [filter, setFilter] = useState(() => tabs.takeIntent()?.filter || lastFilter)
    const [limit, setLimit] = useState(PAGE)
    const {background} = sdk.session.use()
    useFavourites()
    useEffect(() => { lastFilter = filter; setLimit(PAGE) }, [filter])
    const machines = useMemo(() => systems.filter((s) => !isApp(s) && data.games.some((g) => g.systemId === s.id)), [systems, data.games])
    const shown = useMemo(() => searchGames(data.games, [], filter), [data.games, filter, favouriteCount()])
    useSpatial(root, {
      allowed: () => homeOwnsPad(sdk) && tabs.get() === 'collection',
      initial: '.jl-grid [data-nav], [data-nav="f-all"]',
      onFocus: (el) => { if (Number(el.dataset.index) >= limit - GROW_BEFORE_END) setLimit((n) => n + PAGE) },
      keys: {l1: () => tabs.step(-1), r1: () => tabs.step(1), y: onSearch, back: () => tabs.go('play')},
    }, [filter])

    const chip = (id, label) => html`<button type="button" key=${id} data-nav=${`f-${id}`}
      className=${`jl-chip ${filter === id ? 'is-on' : ''}`} aria-pressed=${String(filter === id)}
      onClick=${() => setFilter(id)}>${label}</button>`
    const label = filter === 'all' ? 'All games' : filter === 'fav' ? 'Favourites' : systemName(systems.find((s) => s.id === filter))
    return html`<section className="jl-page jl-collection" ref=${root} aria-labelledby="jl-col-title">
      <div className="jl-head">
        <div><span className="jl-eyebrow">Collection</span><h1 id="jl-col-title">Pick the next game.</h1></div>
        <div className="jl-count"><strong>${String(shown.length).padStart(2, '0')}</strong><span>${label}</span></div>
      </div>
      <div className="jl-chips" role="group" aria-label="Filtrer la collection">
        ${chip('all', `All games (${data.games.length})`)}
        ${chip('fav', html`<${Icon} name="star" filled=${filter === 'fav'} />Favourites (${favouriteCount()})`)}
        ${machines.map((m) => chip(m.id, systemMark(m)))}
        <${chips.SearchChip} nav="f-search" onClick=${onSearch} /><${chips.StyleChip} nav="f-style" />
      </div>
      <${Body} data=${data} shown=${shown} filter=${filter} limit=${limit} background=${background}
        onRetry=${actions.retry} onShowAll=${() => setFilter('all')} onDetails=${onDetails} />
      <${Footer} hints=${hints} />
    </section>`
  }
}
