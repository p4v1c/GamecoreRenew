import {duration} from '../lib/format.js'
import {systemName, systemMaker, systemYear, coverColor, consoleArt, plural} from '../lib/catalog.js'
import {isFavourite, favouriteCount, createUseFavourites} from '../lib/favourites.js'
import {createSpatial, libraryOwnsPad} from '../lib/spatial.js'

const HINTS = [['← → ↑ ↓', 'Naviguer'], ['✕', 'Fiche'], ['○', 'Consoles'], ['△', 'Rechercher'],
  ['L1 R1', 'Onglets'], ['Options', 'Options du jeu']]

/** A console's games: the host's library screen, drawn in Jelly.
 *
 * Loading, sorting, the search keyboard (△), per-game options (Options) and
 * the launch itself stay the host's. This view moves the cursor over its own
 * grid (`libraryOmit` nav/confirm/sort in index.js) and keeps the host's
 * selection on the focused card, so Options and Play act on what is lit.
 */
export function createLibrary(sdk, {tabs, cards, Footer, Details}) {
  const {html, useState, useEffect, useRef, useMemo} = sdk.ui
  const PadKey = sdk.ui.PadKey || (({k}) => html`<kbd>${k}</kbd>`)
  const useSpatial = createSpatial(sdk)
  const useFavourites = createUseFavourites(sdk)

  return function Library(props) {
    const {systemId, system, games, totalCount, playtime, selectedIdx, sort, sortKeys, sortLabels,
      search, loading, loadError, onSelect, onLaunch, onBack, onRetry, onSort, onSearch,
      onOpenSearch, onOpenOptions, detailGame} = props
    const root = useRef(null)
    const [favOnly, setFavOnly] = useState(false)
    const [details, setDetails] = useState(null)
    const {background} = sdk.session.use()
    useFavourites()
    useEffect(() => { setFavOnly(false); setDetails(null) }, [systemId])

    // The host's rows, in the shape every Jelly card takes.
    const rows = useMemo(() => games.map((g, i) => {
      const sid = g.system_id || systemId
      const p = playtime?.[systemId === '__all__' ? `${sid}:${g.filename}` : g.filename]
      return {kind: 'game', key: `${sid}:${g.filename}`, systemId: sid, system, gameKey: g.filename,
        path: g.path, title: g.display_name || sdk.format.gameName(g.filename), ext: g.ext,
        seconds: p?.total_secs || 0, lastPlayed: p?.last_played || null, index: i}
    }), [games, playtime, systemId, system])
    const shown = useMemo(() => favOnly ? rows.filter((r) => isFavourite(r.systemId, r.gameKey)) : rows,
      [rows, favOnly, favouriteCount()])

    useSpatial(root, {
      allowed: () => libraryOwnsPad(sdk),
      initial: `[data-index="${selectedIdx}"], .jl-grid [data-nav]`,
      onFocus: (el) => {
        const i = Number(el.dataset.index)
        if (Number.isFinite(i) && i !== sdk.nav.get().selectedGameIdx) onSelect(i)
      },
      keys: {l1: () => tabs.step(-1), r1: () => tabs.step(1)},
    }, [systemId, loading, favOnly, sort, search])

    const play = (row) => { onSelect(row.index); onLaunch() }
    const label = systemId === '__all__' ? 'Tous les jeux' : systemName(system)

    return html`<main className="jl-main" data-tab="library">
      <section className="jl-page jl-library" ref=${root} aria-labelledby="jl-lib-title"
               style=${{'--cover': coverColor(sdk, system)}}>
        <div className="jl-head">
          <div className="jl-lib-title">
            ${systemId !== '__all__' ? html`<img className="jl-lib-photo" src=${consoleArt(sdk, system)} alt=""
              onError=${(e) => { e.currentTarget.hidden = true }} />` : null}
            <div><span className="jl-eyebrow">${[systemMaker(system), systemYear(system)].filter(Boolean).join(' · ') || 'Ta console'}</span>
              <h1 id="jl-lib-title">${label}</h1></div>
          </div>
          <div className="jl-count"><strong>${String(shown.length).padStart(2, '0')}</strong>
            <span>sur ${plural(totalCount, 'jeu', 'jeux')}</span></div>
        </div>
        <div className="jl-chips" role="group" aria-label="Trier et filtrer">
          <button type="button" className="jl-chip" data-nav="back" onClick=${onBack}>← Consoles</button>
          ${sortKeys.map((k) => html`<button type="button" key=${k} data-nav=${`sort-${k}`}
            className=${`jl-chip ${sort === k ? 'is-on' : ''}`} aria-pressed=${String(sort === k)}
            onClick=${() => onSort(k)}>${{name: 'A → Z', lastPlayed: 'Récents', playtime: 'Les plus joués'}[k] || sortLabels[k]}</button>`)}
          <button type="button" data-nav="fav" className=${`jl-chip ${favOnly ? 'is-on' : ''}`}
            aria-pressed=${String(favOnly)} onClick=${() => setFavOnly((v) => !v)}>★ Favoris</button>
          <button type="button" className="jl-chip jl-chip-search" data-nav="search" onClick=${onOpenSearch}>
            ⌕ ${search ? `« ${search} »` : 'Rechercher'}<${PadKey} k="△" /></button>
          ${search ? html`<button type="button" className="jl-chip" data-nav="clear"
            onClick=${() => onSearch('')}>Effacer la recherche</button>` : null}
          ${detailGame ? html`<button type="button" className="jl-chip" data-nav="options"
            onClick=${onOpenOptions}>Options du jeu<${PadKey} k="Options" /></button>` : null}
        </div>

        ${loadError ? html`<div className="jl-empty"><b>Cette console ne répond pas.</b>
            <p>La liste de ses jeux n’a pas pu être lue.</p>
            <button type="button" className="jl-play" data-nav="retry" onClick=${onRetry}>Réessayer</button></div>`
          : loading ? html`<div className="jl-empty" role="status"><b>On ouvre ${label}…</b></div>`
          : !shown.length ? html`<div className="jl-empty">
              <b>${favOnly ? 'Pas de favori sur cette console.' : search ? 'Aucun jeu trouvé.' : 'Pas encore de jeu ici.'}</b>
              <p>${favOnly ? 'Ouvre la fiche d’un jeu et appuie sur △ pour l’ajouter.'
                : search ? 'Essaie un autre mot avec △.' : 'Ajoute des jeux à cette console pour les voir ici.'}</p></div>`
          : html`<div className="jl-grid">
              ${shown.map((r) => html`<${cards.GameCard} key=${r.key} game=${r} nav=${`g-${r.key}`}
                index=${r.index} held=${!!cards.heldGame(background, r)} onPress=${() => setDetails(r)}
                meta=${duration(r.seconds)} />`)}
            </div>`}
        <${Footer} hints=${HINTS} />
      </section>
      ${details ? html`<${Details} game=${details} onClose=${() => setDetails(null)}
        onPlay=${() => play(details)} />` : null}
    </main>`
  }
}
