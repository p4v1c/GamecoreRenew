import {duration} from '../lib/format.js'
import {coverColor, systemName} from '../lib/catalog.js'
import {isFavourite} from '../lib/favourites.js'

/** The game card: a jelly cover with the jacket on it, and a caption. Used by
 * Play, Collection, the console library and search, so a game looks the same
 * wherever it is found. */
export function createCards(sdk, art) {
  const {html} = sdk.ui
  const {Jacket} = art

  /** Is this game the one frozen in the background? */
  const heldGame = (background, game) => background.find((s) =>
    s.gameKey === game.gameKey && s.systemId === game.systemId) || null

  function Cover({game, big = false}) {
    return html`<span className=${`jl-cover ${big ? 'jl-cover-big' : ''}`}
                      style=${{'--cover': coverColor(sdk, game.system)}}>
      <${Jacket} systemId=${game.systemId} filename=${game.gameKey} title=${game.title} />
      ${isFavourite(game.systemId, game.gameKey)
        ? html`<span className="jl-fav-dot" aria-label="Favori">★</span>` : null}
    </span>`
  }

  function GameCard({game, nav, held, onPress, meta, index}) {
    const line = meta ?? [systemName(game.system),
      game.seconds ? duration(game.seconds) : null].filter(Boolean).join(' · ')
    return html`<button type="button" className="jl-card" data-nav=${nav} data-index=${index}
                        aria-label=${`${game.title}, ${systemName(game.system)}`} onClick=${onPress}>
      <${Cover} game=${game} />
      ${held ? html`<span className="jl-badge">En pause</span>` : null}
      <span className="jl-card-caption">
        <strong>${game.title}</strong>
        <span>${line}</span>
      </span>
    </button>`
  }

  return {GameCard, Cover, heldGame}
}
