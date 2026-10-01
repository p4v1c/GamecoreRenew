import {duration} from '../../lib/format.js'
import {systemName, systemMaker, systemYear, coverColor, consoleArt, plural} from '../../lib/catalog.js'
import {isFavourite, favouriteCount, createUseFavourites} from '../../lib/favourites.js'
import {createSpatial} from '../../lib/spatial.js'
import {libraryOwnsPad} from '../../lib/presses.js'
import {heldSession} from '../../lib/launch.js'
import {libraryRows} from './rows.js'
import {createToolbar} from './toolbar.js'

const HINTS = [['← → ↑ ↓', 'Naviguer'], ['✕', 'Fiche'], ['○', 'Consoles'], ['△', 'Rechercher'],
  ['L1 R1', 'Onglets'], ['Options', 'Options du jeu']]

/** A console's games: the host's library screen, drawn in Jelly. Loading,
 * sort, △ search, per-game options and the launch stay the host's; the host's
 * selection follows the focused card, so Options and Play act on it. */
export function createLibrary(sdk, {tabs, cards, chips, Icon, Footer, Details}) {
  const {html, useState, useEffect, useRef, useMemo} = sdk.ui
  const useSpatial = createSpatial(sdk)
  const useFavourites = createUseFavourites(sdk)
  const Toolbar = createToolbar(sdk, {chips, Icon})

  function Body({props, shown, favOnly, label, background, onOpen}) {
    const {loadError, loading, search, onRetry} = props
    if (loadError) {
      return html`<div className="jl-empty"><b>Cette console ne répond pas.</b><p>La liste de ses jeux n’a pas été lue.</p>
        <button type="button" className="jl-play" data-nav="retry" onClick=${onRetry}>Réessayer</button></div>`
    }
    if (loading) return html`<div className="jl-empty" role="status"><b>On ouvre ${label}.</b></div>`
    if (!shown.length) {
      return html`<div className="jl-empty">
        <b>${favOnly ? 'Pas de favori sur cette console.' : search ? 'Aucun jeu trouvé.' : 'Pas encore de jeu ici.'}</b>
        <p>${favOnly ? 'Ouvre la fiche d’un jeu et appuie sur △ pour l’ajouter.'
          : search ? 'Essaie un autre mot avec △.' : 'Ajoute des jeux à cette console pour les voir ici.'}</p></div>`
    }
    return html`<div className="jl-grid">${shown.map((r) => html`<${cards.GameCard} key=${r.key} game=${r}
      nav=${`g-${r.key}`} index=${r.index} held=${!!heldSession(background, r)} onPress=${() => onOpen(r)}
      meta=${duration(r.seconds)} />`)}</div>`
  }

  return function Library(props) {
    const {systemId, system, totalCount, selectedIdx, sort, search, loading, onSelect, onLaunch} = props
    const root = useRef(null)
    const [favOnly, setFavOnly] = useState(false)
    const [details, setDetails] = useState(null)
    const {background} = sdk.session.use()
    useFavourites()
    useEffect(() => { setFavOnly(false); setDetails(null) }, [systemId])
    const rows = useMemo(() => libraryRows(sdk, props), [props.games, props.playtime, systemId, system])
    const shown = useMemo(() => (favOnly ? rows.filter((r) => isFavourite(r.systemId, r.gameKey)) : rows),
      [rows, favOnly, favouriteCount()])
    useSpatial(root, {
      allowed: () => libraryOwnsPad(sdk),
      initial: `[data-index="${selectedIdx}"], .jl-grid [data-nav]`,
      onFocus: (el) => { const i = Number(el.dataset.index); if (Number.isFinite(i) && i !== sdk.nav.get().selectedGameIdx) onSelect(i) },
      keys: {l1: () => tabs.step(-1), r1: () => tabs.step(1)},
    }, [systemId, loading, favOnly, sort, search])

    const label = systemId === '__all__' ? 'Tous les jeux' : systemName(system)
    const maker = [systemMaker(system), systemYear(system)].filter(Boolean).join(', ')
    return html`<main className="jl-main" data-tab="library">
      <section className="jl-page jl-library" ref=${root} aria-labelledby="jl-lib-title" style=${{'--cover': coverColor(sdk, system)}}>
        <div className="jl-head">
          <div className="jl-lib-title">
            ${systemId !== '__all__' ? html`<img className="jl-lib-photo" src=${consoleArt(sdk, system)} alt=""
              onError=${(e) => { e.currentTarget.hidden = true }} />` : null}
            <div><span className="jl-eyebrow">${maker || 'Ta console'}</span><h1 id="jl-lib-title">${label}</h1></div>
          </div>
          <div className="jl-count"><strong>${String(shown.length).padStart(2, '0')}</strong><span>sur ${plural(totalCount, 'jeu', 'jeux')}</span></div>
        </div>
        <${Toolbar} props=${props} favOnly=${favOnly} onFavOnly=${() => setFavOnly((v) => !v)} />
        <${Body} props=${props} shown=${shown} favOnly=${favOnly} label=${label} background=${background} onOpen=${setDetails} />
        <${Footer} hints=${HINTS} />
      </section>
      ${details ? html`<${Details} game=${details} onClose=${() => setDetails(null)}
        onPlay=${() => { onSelect(details.index); onLaunch() }} />` : null}
    </main>`
  }
}
