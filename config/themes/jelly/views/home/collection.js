import {isApp, systemMark, systemName, plural} from '../../lib/catalog.js'
import {isFavourite, favouriteCount, createUseFavourites} from '../../lib/favourites.js'
import {createSpatial, homeOwnsPad} from '../../lib/spatial.js'

// Cards drawn at once. A box with thousands of games grows the grid as the
// cursor nears its end, instead of building every card up front.
const PAGE = 40

/** Collection: every game, filtered by console or favourites. */
export function createCollectionTab(sdk, {tabs, cards, Footer, hints}) {
  const {html, useState, useEffect, useRef, useMemo} = sdk.ui
  const {Fragment} = sdk.ui.React
  const PadKey = sdk.ui.PadKey || (({k}) => html`<kbd>${k}</kbd>`)
  const useSpatial = createSpatial(sdk)
  const useFavourites = createUseFavourites(sdk)

  // Kept across tab switches, so coming back finds the same filter.
  let lastFilter = 'all'

  return function CollectionTab({data, systems, actions, onDetails, onSearch}) {
    const root = useRef(null)
    const [filter, setFilter] = useState(() => tabs.takeIntent()?.filter || lastFilter)
    const [limit, setLimit] = useState(PAGE)
    const {background} = sdk.session.use()
    useFavourites()
    useEffect(() => { lastFilter = filter; setLimit(PAGE) }, [filter])

    const machines = useMemo(() => systems.filter((s) => !isApp(s)
      && data.games.some((g) => g.systemId === s.id)), [systems, data.games])
    const shown = useMemo(() => data.games.filter((g) => filter === 'all' ? true
      : filter === 'fav' ? isFavourite(g.systemId, g.gameKey) : g.systemId === filter),
    [data.games, filter, favouriteCount()])
    const label = filter === 'all' ? 'Tous les jeux' : filter === 'fav' ? 'Favoris'
      : systemName(systems.find((s) => s.id === filter))

    useSpatial(root, {
      allowed: () => homeOwnsPad(sdk) && tabs.get() === 'collection',
      initial: '.jl-grid [data-nav], [data-nav="f-all"]',
      onFocus: (el) => {
        const i = Number(el.dataset.index)
        if (Number.isFinite(i) && i >= limit - 10) setLimit((n) => n + PAGE)
      },
      keys: {l1: () => tabs.step(-1), r1: () => tabs.step(1), y: onSearch,
        back: () => tabs.go('play')},
    }, [filter])

    const chip = (id, text) => html`<button type="button" key=${id} data-nav=${`f-${id}`}
      className=${`jl-chip ${filter === id ? 'is-on' : ''}`} aria-pressed=${String(filter === id)}
      onClick=${() => setFilter(id)}>${text}</button>`

    return html`<section className="jl-page jl-collection" ref=${root} aria-labelledby="jl-col-title">
      <div className="jl-head">
        <div><span className="jl-eyebrow">La collection</span>
          <h1 id="jl-col-title">Le choix du prochain jeu.</h1></div>
        <div className="jl-count"><strong>${String(shown.length).padStart(2, '0')}</strong>
          <span>${label}</span></div>
      </div>
      <div className="jl-chips" role="group" aria-label="Filtrer la collection">
        ${chip('all', `Tous les jeux · ${data.games.length}`)}
        ${chip('fav', `★ Favoris · ${favouriteCount()}`)}
        ${machines.map((m) => chip(m.id, systemMark(m)))}
        <button type="button" className="jl-chip jl-chip-search" data-nav="f-search" onClick=${onSearch}>
          ⌕ Rechercher<${PadKey} k="△" /></button>
      </div>
      ${data.status === 'error' ? html`<div className="jl-empty">
          <b>La collection ne répond pas.</b><p>Aucune console n’a pu donner sa liste de jeux.</p>
          <button type="button" className="jl-play" data-nav="retry" onClick=${actions.retry}>Réessayer</button></div>`
        : (data.status === 'loading' || data.status === 'idle') && !data.games.length
          ? html`<div className="jl-empty" role="status"><b>On ouvre la boîte à jeux…</b></div>`
        : !shown.length ? html`<div className="jl-empty">
            <b>${filter === 'fav' ? 'Pas encore de favori.' : 'Rien ici pour l’instant.'}</b>
            <p>${filter === 'fav' ? 'Ouvre la fiche d’un jeu et appuie sur △ pour l’ajouter.'
              : 'Ajoute des jeux à tes consoles pour les retrouver ici.'}</p>
            ${filter !== 'all' ? html`<button type="button" className="jl-play" data-nav="show-all"
              onClick=${() => setFilter('all')}>Voir tous les jeux</button>` : null}</div>`
        : html`<${Fragment}><div className="jl-grid">
            ${shown.slice(0, limit).map((g, i) => html`<${cards.GameCard} key=${g.key} game=${g}
              nav=${`g-${g.key}`} index=${i} held=${!!cards.heldGame(background, g)}
              onPress=${() => onDetails(g)} />`)}
          </div>
          ${shown.length > limit ? html`<p className="jl-more">${plural(shown.length - limit, 'autre jeu', 'autres jeux')} plus bas</p>` : null}<//>`}
      <${Footer} hints=${hints} />
    </section>`
  }
}
