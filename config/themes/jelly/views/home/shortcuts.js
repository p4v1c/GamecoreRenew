import {plural} from '../../lib/catalog.js'

/** The two cards beside the hero: favourites, and a random game. */
export function createShortcuts(sdk, {Icon}) {
  const {html} = sdk.ui

  function Card({nav, sun, icon, eyebrow, title, line, disabled, onClick}) {
    return html`<button type="button" className=${`jl-side-card ${sun ? 'jl-side-sun' : ''}`}
                        data-nav=${nav} disabled=${disabled} onClick=${onClick}>
      <span className="jl-side-icon"><${Icon} name=${icon} filled=${icon === 'star'} /></span>
      <span><span className="jl-eyebrow">${eyebrow}</span><b>${title}</b><small>${line}</small></span>
      <span className="jl-arrow"><${Icon} name="out" /></span>
    </button>`
  }

  return function Shortcuts({favourites, gameCount, loading, onFavourites, onSurprise}) {
    return html`<div className="jl-side">
      <${Card} nav="side-fav" icon="star" eyebrow="Within reach" title="Favourites"
        line=${favourites ? plural(favourites, 'game', 'games') : 'Mark a game with △ from its details'}
        disabled=${loading} onClick=${onFavourites} />
      <${Card} nav="side-surprise" sun=${true} icon="dice" eyebrow="Something different" title="Surprise me"
        line="A random game from your collection" disabled=${!gameCount} onClick=${onSurprise} />
    </div>`
  }
}
