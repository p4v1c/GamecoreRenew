import {duration} from '../lib/format.js'
import {coverColor, systemName} from '../lib/catalog.js'
import {isFavourite} from '../lib/favourites.js'

/** The game card: a jelly cover with the jacket on it, and a caption. Play,
 * Collection, a console's library and the search all use it. */
export function createCards(sdk, {art, Icon}) {
  const {html} = sdk.ui
  const {Jacket} = art

  function Cover({game, big = false}) {
    return html`<span className=${`jl-cover ${big ? 'jl-cover-big' : ''}`}
                      style=${{'--cover': coverColor(sdk, game.system)}}>
      <${Jacket} systemId=${game.systemId} filename=${game.gameKey} title=${game.title} />
      ${isFavourite(game.systemId, game.gameKey)
        ? html`<span className="jl-fav-dot" aria-label="Favourite"><${Icon} name="star" filled=${true} /></span>` : null}
    </span>`
  }

  function GameCard({game, nav, held, onPress, meta, index}) {
    const line = meta ?? (game.seconds
      ? `${systemName(game.system)}, ${duration(sdk, game.seconds)} played` : systemName(game.system))
    return html`<button type="button" className="jl-card" data-nav=${nav} data-index=${index}
                        aria-label=${`${game.title}, ${systemName(game.system)}`} onClick=${onPress}>
      <${Cover} game=${game} />
      ${held ? html`<span className="jl-badge">En pause</span>` : null}
      <span className="jl-card-caption"><strong>${game.title}</strong><span>${line}</span></span>
    </button>`
  }

  return {GameCard, Cover}
}
