import {lastPlayed} from '../../lib/format.js'
import {systemName} from '../../lib/catalog.js'
import {byRecent} from '../../lib/collection.js'
import {favouriteCount, createUseFavourites} from '../../lib/favourites.js'
import {createSpatial} from '../../lib/spatial.js'
import {homeOwnsPad} from '../../lib/presses.js'
import {playOrResume, heldSession, launchError} from '../../lib/launch.js'
import {createHero, pickHero} from './hero.js'
import {createShortcuts} from './shortcuts.js'

/** Jouer: the game to pick up, two shortcuts, and the last few adventures. */
export function createPlayTab(sdk, {tabs, cards, Icon, Footer, hints}) {
  const {html, useState, useRef, useMemo} = sdk.ui
  const {Fragment} = sdk.ui.React
  const useSpatial = createSpatial(sdk)
  const useFavourites = createUseFavourites(sdk)
  const Hero = createHero(sdk, {cards, Icon})
  const Shortcuts = createShortcuts(sdk, {Icon})

  function Recent({games, background, onDetails}) {
    if (!games.length) return null
    const played = games.some((g) => g.lastPlayed)
    return html`<${Fragment}><div className="jl-rail-head">
        <h2>${played ? 'Tes dernières aventures' : 'Dans ta collection'}</h2>
        <button type="button" className="jl-text-button" data-nav="all"
                onClick=${() => tabs.go('collection')}>Toute la collection</button>
      </div>
      <div className="jl-row">
        ${games.map((g, i) => html`<${cards.GameCard} key=${g.key} game=${g} nav=${`recent-${g.key}`}
          index=${i} held=${!!heldSession(background, g)} onPress=${() => onDetails(g)}
          meta=${g.lastPlayed ? `${systemName(g.system)}, ${lastPlayed(g.lastPlayed).toLowerCase()}` : systemName(g.system)} />`)}
      </div><//>`
  }

  return function PlayTab({data, actions, onDetails, onSearch}) {
    const root = useRef(null)
    const [error, setError] = useState('')
    const {background} = sdk.session.use()
    useFavourites()
    const games = data.games
    const hero = useMemo(() => pickHero(games, background), [games, background])
    const recent = useMemo(() => {
      const played = byRecent(games).filter((g) => g.lastPlayed)
      return (played.length ? played : games).slice(0, 5)
    }, [games])
    const start = () => {
      setError('')
      Promise.resolve(playOrResume(sdk, hero.game, background)).catch((e) => setError(launchError(e)))
    }
    useSpatial(root, {
      allowed: () => homeOwnsPad(sdk) && tabs.get() === 'play',
      initial: '[data-nav="hero-play"], [data-nav="side-fav"]',
      keys: {l1: () => tabs.step(-1), r1: () => tabs.step(1), y: onSearch},
    }, [games.length > 0])

    return html`<section className="jl-page jl-playpage" ref=${root} aria-labelledby="jl-play-title">
      <div className="jl-head">
        <div><span className="jl-eyebrow">Ton terrain de jeu</span>
          <h1 id="jl-play-title">À toi de jouer<span className="jl-bang">!</span></h1></div>
        <div className="jl-count"><strong>${String(games.length).padStart(2, '0')}</strong>
          <span>${games.length === 1 ? 'jeu' : 'jeux'}<br />à explorer</span></div>
      </div>
      <div className="jl-hero-grid">
        ${hero ? html`<${Hero.Filled} hero=${hero} error=${error} onStart=${start} onDetails=${() => onDetails(hero.game)} />`
          : html`<${Hero.Empty} status=${data.status} onRetry=${actions.retry} onSettings=${() => actions.settings?.()} />`}
        <${Shortcuts} favourites=${favouriteCount()} gameCount=${games.length}
          loading=${data.status === 'loading' || data.status === 'idle'}
          onFavourites=${() => tabs.go('collection', {filter: 'fav'})}
          onSurprise=${() => onDetails(games[Math.floor(Math.random() * games.length)])} />
      </div>
      <${Recent} games=${recent} background=${background} onDetails=${onDetails} />
      <${Footer} hints=${hints} />
    </section>`
  }
}
