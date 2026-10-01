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
      <${Card} nav="side-fav" icon="star" eyebrow="Le meilleur, à portée" title="Mes favoris"
        line=${favourites ? `${plural(favourites, 'jeu', 'jeux')} qui font plaisir` : 'Marque un jeu avec △ depuis sa fiche'}
        disabled=${loading} onClick=${onFavourites} />
      <${Card} nav="side-surprise" sun=${true} icon="dice" eyebrow="On change un peu ?" title="Surprends-moi"
        line="Un jeu au hasard de ta collection" disabled=${!gameCount} onClick=${onSurprise} />
    </div>`
  }
}
