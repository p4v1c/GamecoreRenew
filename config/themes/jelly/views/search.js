import {duration} from '../lib/format.js'
import {isApp, systemMark, systemName, plural} from '../lib/catalog.js'
import {fold} from '../lib/collection.js'
import {isFavourite, favouriteCount, createUseFavourites} from '../lib/favourites.js'
import {createSpatial, layerOwnsPad, currentPress} from '../lib/spatial.js'
import {createKeyboard} from './keyboard.js'
import {createUseLayer} from './details.js'

const ZONES = [['keys', 'Clavier'], ['filters', 'Filtres'], ['games', 'Jeux']]
const PAGE = 30

/** "La bonne pioche": the whole collection, searched from the pad.
 *
 * Three zones, and the pad stays in the one that is lit: the keyboard, the
 * filters, the results. L1/R1 walk the zones, △ jumps between the keyboard and
 * the results and remembers where it was in each, ○ comes back to the keyboard
 * and then closes. There is no text field to land on: the query is typed with
 * the keyboard and only shown above it.
 */
export function createSearch(sdk, {cards, Details}) {
  const {html, useState, useEffect, useRef, useMemo} = sdk.ui
  const PadKey = sdk.ui.PadKey || (({k}) => html`<kbd>${k}</kbd>`)
  const useSpatial = createSpatial(sdk)
  const useLayer = createUseLayer(sdk)
  const useFavourites = createUseFavourites(sdk)
  const Keyboard = createKeyboard(sdk)

  // The query survives closing the panel within one visit to the box, the way
  // a search bar keeps what was typed in it.
  let kept = {query: '', filter: 'all'}

  /** Every word of the query must appear in the title or the console. */
  const matches = (game, words) => {
    if (!words.length) return true
    const hay = fold(`${game.title} ${systemName(game.system)} ${systemMark(game.system)}`)
    return words.every((w) => hay.includes(w))
  }

  return function Search({data, systems, onClose}) {
    const depth = useLayer()
    const keysRef = useRef(null)
    const filtersRef = useRef(null)
    const gamesRef = useRef(null)
    const [query, setQuery] = useState(kept.query)
    const [filter, setFilter] = useState(kept.filter)
    const [page, setPage] = useState('letters')
    const [zone, setZoneState] = useState('keys')
    // Read by the handlers: two presses inside one frame must see the zone
    // the first one moved to, not the one the last render saw.
    const zoneRef = useRef('keys')
    const setZone = (z) => { zoneRef.current = z; setZoneState(z) }
    const [limit, setLimit] = useState(PAGE)
    const [details, setDetails] = useState(null)
    const {background} = sdk.session.use()
    useFavourites()
    useEffect(() => { kept = {query, filter}; setLimit(PAGE) }, [query, filter])

    const machines = useMemo(() => systems.filter((s) => !isApp(s)
      && data.games.some((g) => g.systemId === s.id)), [systems, data.games])
    const words = useMemo(() => fold(query).split(/\s+/).filter(Boolean), [query])
    const results = useMemo(() => data.games.filter((g) =>
      (filter === 'all' || (filter === 'fav' ? isFavourite(g.systemId, g.gameKey) : g.systemId === filter))
      && matches(g, words)), [data.games, words, filter, favouriteCount()])

    const type = (k) => setQuery((q) => (q + k).slice(0, 60))
    const erase = () => setQuery((q) => q.slice(0, -1))
    const clearAll = () => { setQuery(''); setFilter('all') }
    const usable = (z) => z !== 'games' || results.length > 0
    const goZone = (z) => { if (usable(z) && z !== zoneRef.current) { sdk.system.playSound('move'); setZone(z) } }
    const cycle = (d) => {
      const at = ZONES.findIndex(([id]) => id === zoneRef.current)
      for (let i = 1; i <= ZONES.length; i++) {
        const next = ZONES[(at + d * i + ZONES.length * 3) % ZONES.length][0]
        if (usable(next)) { goZone(next); return }
      }
    }
    // A zone left empty by a new filter hands the pad back to the keyboard.
    useEffect(() => { if (zone === 'games' && !results.length) setZone('keys') }, [results.length])

    const keys = {
      l1: () => cycle(-1), r1: () => cycle(1),
      x: erase, l2: clearAll,
      y: () => goZone(zoneRef.current === 'games' ? 'keys' : 'games'),
      back: () => (zoneRef.current === 'keys' ? onClose() : goZone('keys')),
    }
    // Each zone's listener asks in turn, and the first to answer moves the
    // zone; the rest must judge the same press by the zone it started in.
    const pressZone = useRef({press: null, zone: 'keys'})
    const zoneAtPress = () => {
      const p = currentPress()
      if (!p) return zoneRef.current
      if (pressZone.current.press !== p) pressZone.current = {press: p, zone: zoneRef.current}
      return pressZone.current.zone
    }
    const owns = (z) => () => zoneAtPress() === z && !details && layerOwnsPad(sdk, depth.current)
    useSpatial(keysRef, {allowed: owns('keys'), initial: '[data-nav="k-A"], [data-nav="k-1"]', keys}, [zone, page])
    useSpatial(filtersRef, {allowed: owns('filters'), initial: '.is-on', keys}, [zone])
    useSpatial(gamesRef, {
      allowed: owns('games'), initial: '[data-nav]', keys,
      onFocus: (el) => {
        const i = Number(el.dataset.index)
        if (Number.isFinite(i) && i >= limit - 6) setLimit((n) => n + PAGE)
      },
    }, [zone])

    const chip = (id, text) => html`<button type="button" key=${id} data-nav=${`sf-${id}`}
      className=${`jl-chip ${filter === id ? 'is-on' : ''}`} aria-pressed=${String(filter === id)}
      onClick=${() => setFilter(id)}>${text}</button>`
    const zoneTab = ([id, label], i) => html`<button type="button" key=${id}
      className=${`jl-zone ${zone === id ? 'is-on' : ''}`} disabled=${!usable(id)}
      aria-pressed=${String(zone === id)} onClick=${() => goZone(id)}>
      <small>0${i + 1}</small>${label}</button>`

    return html`<div className="jl-scrim">
      <section className="jl-dialog jl-search" role="dialog" aria-modal="true" aria-labelledby="jl-search-title">
        <header className="jl-search-head">
          <div><span className="jl-eyebrow">Cherche. Trouve. Joue.</span>
            <h2 id="jl-search-title">La bonne pioche.</h2></div>
          <button type="button" className="jl-close" aria-label="Fermer la recherche" onClick=${onClose}>×</button>
        </header>
        <div className="jl-query" aria-live="polite">
          <span className="jl-query-icon" aria-hidden="true">⌕</span>
          <span className=${`jl-query-text ${query ? '' : 'is-empty'}`}>${query || 'Un jeu, une console…'}</span>
          ${zone === 'keys' ? html`<i className="jl-caret" aria-hidden="true" />` : null}
          <span className="jl-live">${data.status === 'ready' ? 'En direct' : 'Chargement…'}</span>
        </div>
        <nav className="jl-zones" aria-label="Zones de recherche">
          <${PadKey} k="L1" />${ZONES.map(zoneTab)}<${PadKey} k="R1" />
        </nav>
        <div className="jl-search-body">
          <div className=${`jl-search-keys ${zone === 'keys' ? 'is-live' : ''}`} ref=${keysRef}>
            <span className="jl-eyebrow">Sous les pouces</span>
            <${Keyboard} page=${page} onKey=${type} onSpace=${() => type(' ')} onDelete=${erase}
              onPage=${() => setPage((p) => (p === 'letters' ? 'symbols' : 'letters'))} />
            <button type="button" className="jl-results-button" data-nav="k-results"
                    disabled=${!results.length} onClick=${() => goZone('games')}>
              Voir ${plural(results.length, 'résultat', 'résultats')}<span aria-hidden="true">→</span></button>
          </div>
          <div className="jl-search-right">
            <div className=${`jl-search-filters ${zone === 'filters' ? 'is-live' : ''}`} ref=${filtersRef}>
              ${chip('all', 'Tout')}
              ${machines.map((m) => chip(m.id, systemMark(m)))}
              ${chip('fav', '★ Favoris')}
            </div>
            <div className="jl-results-head"><b>${words.length ? 'Résultats' : 'À découvrir'}</b>
              <span>${plural(results.length, 'jeu', 'jeux')}</span></div>
            <div className=${`jl-results ${zone === 'games' ? 'is-live' : ''}`} ref=${gamesRef}>
              ${results.length ? results.slice(0, limit).map((g, i) => html`<button type="button" key=${g.key}
                  className="jl-result" data-nav=${`r-${g.key}`} data-index=${i}
                  onClick=${() => setDetails(g)}>
                  <${cards.Cover} game=${g} />
                  <span className="jl-result-text"><small>${systemName(g.system)}</small><b>${g.title}</b>
                    <i>${duration(g.seconds)}${
                      isFavourite(g.systemId, g.gameKey) ? ' · ★' : ''}${
                      cards.heldGame(background, g) ? ' · en pause' : ''}</i></span>
                </button>`)
                : html`<div className="jl-empty jl-empty-small">
                    <b>${data.status === 'error' ? 'La collection ne répond pas.' : 'Aucun jeu ne correspond.'}</b>
                    <p>${words.length || filter !== 'all' ? 'Essaie un autre mot, ou vide tout avec L2.' : 'Ajoute des jeux à tes consoles.'}</p>
                  </div>`}
            </div>
          </div>
        </div>
        <footer className="jl-search-foot">
          <span><${PadKey} k="← → ↑ ↓" />Naviguer</span><span><${PadKey} k="✕" />Choisir</span>
          <span><${PadKey} k="□" />Effacer</span><span><${PadKey} k="L2" />Tout vider</span>
          <span><${PadKey} k="△" />Clavier / jeux</span><span><${PadKey} k="L1 R1" />Zones</span>
          <span><${PadKey} k="○" />${zone === 'keys' ? 'Fermer' : 'Clavier'}</span>
        </footer>
      </section>
      ${details ? html`<${Details} game=${details} onClose=${() => setDetails(null)} />` : null}
    </div>`
  }
}
