// The host's sort keys, in Jelly's words; an unknown key keeps the host's label.
const SORTS = {name: 'De A à Z', lastPlayed: 'Récents', playtime: 'Les plus joués'}

/** The chips over a console's games: back, sort, favourites, search, art, options. */
export function createToolbar(sdk, {chips, Icon}) {
  const {html} = sdk.ui
  const PadKey = sdk.ui.PadKey || (({k}) => html`<kbd>${k}</kbd>`)

  return function Toolbar({props, favOnly, onFavOnly}) {
    const {sort, sortKeys, sortLabels, search, detailGame, onBack, onSort, onSearch, onOpenSearch, onOpenOptions} = props
    const chip = (nav, on, label, onClick) => html`<button type="button" key=${nav} data-nav=${nav}
      className=${`jl-chip ${on ? 'is-on' : ''}`} aria-pressed=${String(on)} onClick=${onClick}>${label}</button>`
    return html`<div className="jl-chips" role="group" aria-label="Trier et filtrer">
      <button type="button" className="jl-chip" data-nav="back" onClick=${onBack}><${Icon} name="back" />Consoles</button>
      ${sortKeys.map((k) => chip(`sort-${k}`, sort === k, SORTS[k] || sortLabels[k], () => onSort(k)))}
      ${chip('fav', favOnly, html`<${Icon} name="star" filled=${favOnly} />Favoris`, onFavOnly)}
      <${chips.SearchChip} nav="search" label=${search ? `« ${search} »` : 'Rechercher'} onClick=${onOpenSearch} />
      ${search ? html`<button type="button" className="jl-chip" data-nav="clear" onClick=${() => onSearch('')}>Effacer la recherche</button>` : null}
      <${chips.StyleChip} nav="style" />
      ${detailGame ? html`<button type="button" className="jl-chip" data-nav="options" onClick=${onOpenOptions}>Options du jeu<${PadKey} k="Options" /></button>` : null}
    </div>`
  }
}
