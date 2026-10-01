import {duration, lastPlayed} from '../../lib/format.js'
import {systemName, coverColor, plural} from '../../lib/catalog.js'
import {byRecent} from '../../lib/collection.js'
import {favouriteCount, createUseFavourites} from '../../lib/favourites.js'
import {createSpatial, homeOwnsPad} from '../../lib/spatial.js'
import {track} from '../../lib/drawings.js'

/** Jouer: the game to pick up, two shortcuts, and the last few adventures. */
export function createPlayTab(sdk, {tabs, cards, Footer, hints}) {
  const {html, useState, useRef, useMemo} = sdk.ui
  const {Fragment} = sdk.ui.React
  const PadKey = sdk.ui.PadKey || (({k}) => html`<kbd>${k}</kbd>`)
  const useSpatial = createSpatial(sdk)
  const useFavourites = createUseFavourites(sdk)

  /** The suspended game first, then the last one played, then any game. */
  const pickHero = (games, background) => {
    const paused = background.find((s) => s.kind !== 'app')
    const held = paused && games.find((g) => g.gameKey === paused.gameKey && g.systemId === paused.systemId)
    if (held) return {game: held, mood: 'paused'}
    const recent = byRecent(games).find((g) => g.lastPlayed)
    if (recent) return {game: recent, mood: 'recent'}
    return games[0] ? {game: games[0], mood: 'new'} : null
  }

  const PILL = {paused: '❚❚ En pause', recent: '↺ Dernière partie', new: '✦ À découvrir'}
  const TITLE = {paused: 'On reprend ?', recent: 'Encore un petit tour ?', new: 'Et si on commençait ?'}

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

    const surprise = () => {
      if (!games.length) return
      onDetails(games[Math.floor(Math.random() * games.length)])
    }
    const start = () => {
      if (!hero) return
      setError('')
      const held = cards.heldGame(background, hero.game)
      const run = held ? sdk.session.resume(held.session)
        : sdk.defaults.launchGame({systemId: hero.game.systemId, path: hero.game.path, gameKey: hero.game.gameKey})
      Promise.resolve(run).catch((e) => setError(e?.message || 'Le jeu n’a pas pu démarrer.'))
    }

    useSpatial(root, {
      allowed: () => homeOwnsPad(sdk) && tabs.get() === 'play',
      initial: '[data-nav="hero-play"], [data-nav="side-fav"]',
      keys: {l1: () => tabs.step(-1), r1: () => tabs.step(1), y: onSearch},
    }, [games.length > 0])

    const favs = favouriteCount()
    const loading = data.status === 'loading' || data.status === 'idle'

    return html`<section className="jl-page jl-playpage" ref=${root} aria-labelledby="jl-play-title">
      <div className="jl-head">
        <div><span className="jl-eyebrow">Ton terrain de jeu</span>
          <h1 id="jl-play-title">À toi de jouer<span className="jl-bang">!</span></h1></div>
        <div className="jl-count"><strong>${String(games.length).padStart(2, '0')}</strong>
          <span>${games.length === 1 ? 'jeu' : 'jeux'}<br />à explorer</span></div>
      </div>

      <div className="jl-hero-grid">
        ${hero ? html`<div className="jl-hero" style=${{'--cover': coverColor(sdk, hero.game.system)}}>
            <div className="jl-hero-art" aria-hidden="true">
              <span dangerouslySetInnerHTML=${{__html: track()}} />
              <span className="jl-hero-jacket"><${cards.Cover} game=${hero.game} big=${true} /></span>
              <span className="jl-hero-tag">Let’s play</span>
            </div>
            <div className="jl-hero-copy">
              <span className="jl-pill">${PILL[hero.mood]}</span>
              <h2>${TITLE[hero.mood]}</h2>
              <p className="jl-hero-game">${hero.game.title}<span> · ${systemName(hero.game.system)}${
                hero.game.seconds ? ` · ${duration(hero.game.seconds)}` : ''}</span></p>
              ${error ? html`<p className="jl-error" role="alert">${error}</p>` : null}
              <div className="jl-hero-actions">
                <button type="button" className="jl-play" data-nav="hero-play" onClick=${start}>
                  ${hero.mood === 'paused' ? 'Reprendre' : 'C’est parti'}<${PadKey} k="✕" /></button>
                <button type="button" className="jl-ghost" data-nav="hero-details"
                        onClick=${() => onDetails(hero.game)}>Voir la fiche</button>
              </div>
            </div>
          </div>`
          : html`<div className="jl-hero jl-hero-empty">
            <div className="jl-hero-art" aria-hidden="true"><span dangerouslySetInnerHTML=${{__html: track()}} /></div>
            <div className="jl-hero-copy">
              <span className="jl-pill">${loading ? '… Un instant' : '✦ Bienvenue'}</span>
              <h2>${loading ? 'On ouvre la boîte à jeux.' : data.status === 'error' ? 'La collection ne répond pas.' : 'Ta collection commence ici.'}</h2>
              <p className="jl-hero-game">${loading ? 'Les consoles et les jeux arrivent.'
                : data.status === 'error' ? 'Aucune console n’a pu donner sa liste de jeux.'
                : 'Installe un émulateur dans Réglages, puis ajoute tes jeux.'}</p>
              <div className="jl-hero-actions">
                ${data.status === 'error'
                  ? html`<button type="button" className="jl-play" data-nav="hero-retry" onClick=${actions.retry}>Réessayer<${PadKey} k="✕" /></button>`
                  : loading ? null
                  : html`<button type="button" className="jl-play" data-nav="hero-settings" onClick=${() => actions.settings?.()}>Ouvrir les réglages<${PadKey} k="✕" /></button>`}
              </div>
            </div>
          </div>`}

        <div className="jl-side">
          <button type="button" className="jl-side-card" data-nav="side-fav" disabled=${loading}
                  onClick=${() => tabs.go('collection', {filter: 'fav'})}>
            <span className="jl-side-icon" aria-hidden="true">★</span>
            <span><span className="jl-eyebrow">Le meilleur, à portée</span>
              <b>Mes favoris</b>
              <small>${favs ? `${plural(favs, 'jeu', 'jeux')} qui font plaisir` : 'Marque un jeu avec △ depuis sa fiche'}</small></span>
            <span className="jl-arrow" aria-hidden="true">↗</span>
          </button>
          <button type="button" className="jl-side-card jl-side-sun" data-nav="side-surprise"
                  disabled=${!games.length} onClick=${surprise}>
            <span className="jl-side-icon" aria-hidden="true">⚄</span>
            <span><span className="jl-eyebrow">On change un peu ?</span>
              <b>Surprends-moi</b><small>Un jeu au hasard de ta collection</small></span>
            <span className="jl-arrow" aria-hidden="true">↗</span>
          </button>
        </div>
      </div>

      ${recent.length ? html`<${Fragment}><div className="jl-rail-head">
          <h2>${recent.some((g) => g.lastPlayed) ? 'Tes dernières aventures' : 'Dans ta collection'}</h2>
          <button type="button" className="jl-text-button" data-nav="all"
                  onClick=${() => tabs.go('collection')}>Toute la collection ↗</button>
        </div>
        <div className="jl-row">
          ${recent.map((g, i) => html`<${cards.GameCard} key=${g.key} game=${g} nav=${`recent-${g.key}`}
            index=${i} held=${!!cards.heldGame(background, g)} onPress=${() => onDetails(g)}
            meta=${[systemName(g.system), g.lastPlayed ? lastPlayed(g.lastPlayed) : null].filter(Boolean).join(' · ')} />`)}
        </div><//>` : null}
      <${Footer} hints=${hints} />
    </section>`
  }
}
