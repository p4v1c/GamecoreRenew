import {duration} from '../../lib/format.js'
import {systemName} from '../../lib/catalog.js'
import {isFavourite} from '../../lib/favourites.js'
import {heldSession} from '../../lib/launch.js'

/** The results zone: two columns of games, or why there are none. */
export function createResults(sdk, {cards}) {
  const {html} = sdk.ui

  const lineOf = (g, background) => [duration(g.seconds),
    isFavourite(g.systemId, g.gameKey) ? 'favori' : null,
    heldSession(background, g) ? 'en pause' : null].filter(Boolean).join(', ')

  return function Results({games, limit, background, status, searching, onPick}) {
    if (!games.length) {
      return html`<div className="jl-empty jl-empty-small">
        <b>${status === 'error' ? 'La collection ne répond pas.' : 'Aucun jeu ne correspond.'}</b>
        <p>${searching ? 'Essaie un autre mot, ou vide tout avec L2.' : 'Ajoute des jeux à tes consoles.'}</p>
      </div>`
    }
    return games.slice(0, limit).map((g, i) => html`<button type="button" key=${g.key}
        className="jl-result" data-nav=${`r-${g.key}`} data-index=${i} onClick=${() => onPick(g)}>
      <${cards.Cover} game=${g} />
      <span className="jl-result-text"><small>${systemName(g.system)}</small><b>${g.title}</b>
        <i>${lineOf(g, background)}</i></span>
    </button>`)
  }
}
