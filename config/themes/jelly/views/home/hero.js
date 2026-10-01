import {duration} from '../../lib/format.js'
import {systemName, coverColor} from '../../lib/catalog.js'
import {byRecent} from '../../lib/collection.js'
import {track} from '../../lib/drawings.js'

const PILL = {paused: 'Paused', recent: 'Last played', new: 'New here'}
const PILL_ICON = {paused: 'pause', recent: 'again', new: 'sparkle'}
const TITLE = {paused: 'Pick it back up', recent: 'One more round', new: 'Start with this one'}

/** The suspended game first, then the last one played, then any game. */
export const pickHero = (games, background) => {
  const paused = background.find((s) => s.kind !== 'app')
  const held = paused && games.find((g) => g.gameKey === paused.gameKey && g.systemId === paused.systemId)
  if (held) return {game: held, mood: 'paused'}
  const recent = byRecent(games).find((g) => g.lastPlayed)
  if (recent) return {game: recent, mood: 'recent'}
  return games[0] ? {game: games[0], mood: 'new'} : null
}

/** The big purple card on Play: the game to pick up, or why there is none. */
export function createHero(sdk, {cards, Icon}) {
  const {html} = sdk.ui
  const PadKey = sdk.ui.PadKey || (({k}) => html`<kbd>${k}</kbd>`)
  const Track = () => html`<span dangerouslySetInnerHTML=${{__html: track()}} />`

  function Filled({hero, error, onStart, onDetails}) {
    const {game, mood} = hero
    return html`<div className="jl-hero" style=${{'--cover': coverColor(sdk, game.system)}}>
      <div className="jl-hero-art" aria-hidden="true"><${Track} />
        <span className="jl-hero-jacket"><${cards.Cover} game=${game} big=${true} /></span>
        <span className="jl-hero-tag">Let’s play</span></div>
      <div className="jl-hero-copy">
        <span className="jl-pill"><${Icon} name=${PILL_ICON[mood]} />${PILL[mood]}</span>
        <h2>${TITLE[mood]}</h2>
        <p className="jl-hero-game">${game.title}<span>, ${systemName(game.system)}${
          game.seconds ? `, ${duration(sdk, game.seconds)} played` : ''}</span></p>
        ${error ? html`<p className="jl-error" role="alert">${error}</p>` : null}
        <div className="jl-hero-actions">
          <button type="button" className="jl-play" data-nav="hero-play" onClick=${onStart}>
            ${mood === 'paused' ? 'Resume' : 'Play'}<${PadKey} k="✕" /></button>
          <button type="button" className="jl-ghost" data-nav="hero-details" onClick=${onDetails}>Details</button>
        </div>
      </div>
    </div>`
  }

  function Empty({status, onRetry, onSettings}) {
    const loading = status === 'loading' || status === 'idle'
    const [title, line] = loading ? ['Opening the game box.', 'Consoles and games are on their way.']
      : status === 'error' ? ['The collection isn’t answering.', 'No console sent its game list.']
        : ['Your collection starts here.', 'Install an emulator in Settings, then add your games.']
    const action = loading ? null : status === 'error'
      ? html`<button type="button" className="jl-play" data-nav="hero-retry" onClick=${onRetry}>Try again<${PadKey} k="✕" /></button>`
      : html`<button type="button" className="jl-play" data-nav="hero-settings" onClick=${onSettings}>Open settings<${PadKey} k="✕" /></button>`
    return html`<div className="jl-hero jl-hero-empty">
      <div className="jl-hero-art" aria-hidden="true"><${Track} /></div>
      <div className="jl-hero-copy">
        <span className="jl-pill">${loading ? 'One moment' : 'Welcome'}</span>
        <h2>${title}</h2><p className="jl-hero-game">${line}</p>
        <div className="jl-hero-actions">${action}</div>
      </div>
    </div>`
  }

  return {Filled, Empty}
}
