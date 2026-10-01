import {plural} from '../../lib/catalog.js'
import {favouriteCount, createUseFavourites} from '../../lib/favourites.js'
import {createSpatial} from '../../lib/spatial.js'
import {layerOwnsPad} from '../../lib/presses.js'
import {wordsOf, searchGames} from '../../lib/search.js'
import {createUseLayer} from '../details.js'
import {createKeyboard} from './keyboard.js'
import {createResults} from './results.js'
import {createUseZones} from './zones.js'
import {createSearchFrame} from './header.js'

const PAGE = 30
/** "La bonne pioche": the whole collection, searched from the pad. Three zones
 * (keyboard, filters, results); the pad stays in the lit one, and there is no
 * text field to land on. Pad rules: theme README, "Pad". */
export function createSearch(sdk, {cards, Details, Icon}) {
  const {html, useState, useEffect, useRef, useMemo} = sdk.ui
  const useSpatial = createSpatial(sdk)
  const useLayer = createUseLayer(sdk)
  const useFavourites = createUseFavourites(sdk)
  const useZones = createUseZones(sdk)
  const Keyboard = createKeyboard(sdk)
  const Results = createResults(sdk, {cards})
  const Frame = createSearchFrame(sdk, {Icon})
  // Kept while the box runs, the way a search bar keeps what was typed in it.
  let kept = {query: '', filter: 'all'}

  /** The three zones' pad bindings, each live only while its zone is lit. */
  function useZonePads(refs, zones, details, keys, onResultFocus) {
    const depth = useLayer()
    const owns = (z) => () => zones.zoneAtPress() === z && !details && layerOwnsPad(sdk, depth.current)
    useSpatial(refs.keys, {allowed: owns('keys'), initial: '[data-nav="k-A"], [data-nav="k-1"]', keys}, [zones.zone])
    useSpatial(refs.filters, {allowed: owns('filters'), initial: '.is-on', keys}, [zones.zone])
    useSpatial(refs.games, {allowed: owns('games'), initial: '[data-nav]', keys, onFocus: onResultFocus}, [zones.zone])
  }

  /** The typed query and the filter, kept between visits. */
  function useQuery(onChange) {
    const [query, setQuery] = useState(kept.query)
    const [filter, setFilter] = useState(kept.filter)
    useEffect(() => { kept = {query, filter}; onChange() }, [query, filter])
    return {query, filter, setFilter, type: (k) => setQuery((q) => (q + k).slice(0, 60)),
      erase: () => setQuery((q) => q.slice(0, -1)), clear: () => { setQuery(''); setFilter('all') }}
  }

  return function Search({data, systems, onClose}) {
    const refs = {keys: useRef(null), filters: useRef(null), games: useRef(null)}
    const [page, setPage] = useState('letters')
    const [limit, setLimit] = useState(PAGE)
    const [details, setDetails] = useState(null)
    const {background} = sdk.session.use()
    useFavourites()
    const {query, filter, setFilter, type, erase, clear} = useQuery(() => setLimit(PAGE))
    const words = useMemo(() => wordsOf(query), [query])
    const results = useMemo(() => searchGames(data.games, words, filter), [data.games, words, filter, favouriteCount()])
    const zones = useZones((z) => z !== 'games' || results.length > 0)
    // A filter that empties the results hands the pad back to the keyboard.
    useEffect(() => { if (zones.current() === 'games' && !results.length) zones.set('keys') }, [results.length])

    useZonePads(refs, zones, details, {
      l1: () => zones.cycle(-1), r1: () => zones.cycle(1), x: erase, l2: clear,
      y: () => zones.go(zones.current() === 'games' ? 'keys' : 'games'),
      back: () => (zones.current() === 'keys' ? onClose() : zones.go('keys')),
    }, (el) => { if (Number(el.dataset.index) >= limit - 6) setLimit((n) => n + PAGE) })

    const lit = (z) => (zones.zone === z ? 'is-live' : '')
    return html`<div className="jl-scrim">
      <section className="jl-dialog jl-search" role="dialog" aria-modal="true" aria-labelledby="jl-search-title">
        <${Frame.Header} query=${query} zone=${zones.zone} ready=${data.status === 'ready'}
          gamesUsable=${results.length > 0} onZone=${zones.go} onClose=${onClose} />
        <div className="jl-search-body">
          <div className=${`jl-search-keys ${lit('keys')}`} ref=${refs.keys}>
            <span className="jl-eyebrow">Sous les pouces</span>
            <${Keyboard} page=${page} onKey=${type} onSpace=${() => type(' ')} onDelete=${erase} Icon=${Icon}
              onPage=${() => setPage((p) => (p === 'letters' ? 'symbols' : 'letters'))} />
            <button type="button" className="jl-results-button" data-nav="k-results" disabled=${!results.length}
              onClick=${() => zones.go('games')}>Voir les ${plural(results.length, 'résultat', 'résultats')}</button>
          </div>
          <div className="jl-search-right">
            <div className=${`jl-search-filters ${lit('filters')}`} ref=${refs.filters}>
              <${Frame.Filters} games=${data.games} systems=${systems} filter=${filter} onFilter=${setFilter} />
            </div>
            <div className="jl-results-head"><b>${words.length ? 'Résultats' : 'À découvrir'}</b>
              <span>${plural(results.length, 'jeu', 'jeux')}</span></div>
            <div className=${`jl-results ${lit('games')}`} ref=${refs.games}>
              <${Results} games=${results} limit=${limit} background=${background} status=${data.status}
                searching=${words.length > 0 || filter !== 'all'} onPick=${setDetails} />
            </div>
          </div>
        </div>
        <${Frame.Foot} zone=${zones.zone} />
      </section>
      ${details ? html`<${Details} game=${details} onClose=${() => setDetails(null)} />` : null}
    </div>`
  }
}
