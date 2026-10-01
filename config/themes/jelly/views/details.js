import {duration, lastPlayed} from '../lib/format.js'
import {systemName, systemYear} from '../lib/catalog.js'
import {isFavourite, toggleFavourite, createUseFavourites} from '../lib/favourites.js'
import {createSpatial} from '../lib/spatial.js'
import {layerOwnsPad} from '../lib/presses.js'
import {playOrResume, heldSession, launchError} from '../lib/launch.js'

/** Raise the modal depth while a layer is up. The depth it lands on is how its
 * handlers know nothing has opened on top of it since. */
export const createUseLayer = (sdk) => function useLayer() {
  const {useEffect, useRef} = sdk.ui
  const depth = useRef(0)
  useEffect(() => {
    sdk.nav.openModal()
    depth.current = sdk.nav.get().modalDepth
    return () => sdk.nav.closeModal()
  }, [])
  return depth
}

/** The facts under the description; empty ones are left out, never a dash. */
const factsOf = (game, meta) => [
  ['Console', systemName(game.system)],
  [meta?.year || systemYear(game.system) ? 'Année' : null, meta?.year || systemYear(game.system)],
  [meta?.developer ? 'Studio' : null, meta?.developer],
  [meta?.genres?.length ? 'Genre' : null, meta?.genres?.slice?.(0, 3).join(', ')],
  [meta?.players ? 'Joueurs' : null, meta?.players_label || String(meta?.players)],
  ['Temps de jeu', duration(game.seconds)],
  [game.lastPlayed ? 'Dernière partie' : null, lastPlayed(game.lastPlayed)],
].filter(([k]) => k)

/** A game's fiche. Play stays open until the launch resolves, so a refusal is
 * said here; a game frozen in the background is resumed, not started twice. */
export function createDetails(sdk, {cards, Icon}) {
  const {html, useState, useEffect, useRef} = sdk.ui
  const PadKey = sdk.ui.PadKey || (({k}) => html`<kbd>${k}</kbd>`)
  const useSpatial = createSpatial(sdk)
  const useLayer = createUseLayer(sdk)
  const useFavourites = createUseFavourites(sdk)

  function useMeta(game) {
    const [meta, setMeta] = useState(null)
    useEffect(() => {
      let alive = true
      sdk.api.metadata.get(game.systemId, game.gameKey)
        .then((m) => { if (alive && m?.found) setMeta(m) })
        .catch(() => { /* no metadata: a shorter fiche */ })
      return () => { alive = false }
    }, [game.key])
    return meta
  }

  return function Details({game, onClose, onPlay}) {
    const root = useRef(null)
    const depth = useLayer()
    const meta = useMeta(game)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    const {background} = sdk.session.use()
    useFavourites()
    const held = heldSession(background, game)
    const fav = isFavourite(game.systemId, game.gameKey)
    const favourite = () => toggleFavourite(game.systemId, game.gameKey)

    const play = async () => {
      if (busy) return
      setBusy(true)
      setError('')
      try {
        await (onPlay && !held ? onPlay(game) : playOrResume(sdk, game, background))
        onClose()
      } catch (e) { setError(launchError(e)); setBusy(false) }
    }
    useSpatial(root, {allowed: () => layerOwnsPad(sdk, depth.current), initial: '[data-nav="play"]',
      keys: {back: onClose, y: favourite}})

    return html`<div className="jl-scrim" onClick=${(e) => { if (e.target === e.currentTarget) onClose() }}>
      <section className="jl-dialog jl-details" ref=${root} role="dialog" aria-modal="true" aria-labelledby="jl-details-title">
        <button type="button" className="jl-close" data-nav="close" aria-label="Fermer la fiche" onClick=${onClose}>×</button>
        <div className="jl-details-art"><${cards.Cover} game=${game} big=${true} /></div>
        <div className="jl-details-copy">
          <span className="jl-eyebrow">${systemName(game.system)}${held ? ', en pause' : ''}</span>
          <h2 id="jl-details-title">${meta?.title || game.title}</h2>
          <p className="jl-details-text">${meta?.description || 'Pas encore de description pour ce jeu.'}</p>
          <dl className="jl-facts">${factsOf(game, meta).map(([k, v]) => html`<div key=${k}><dt>${k}</dt><dd>${v}</dd></div>`)}</dl>
          ${error ? html`<p className="jl-error" role="alert">${error}</p>` : null}
          <div className="jl-actions">
            <button type="button" className="jl-play" data-nav="play" disabled=${busy} onClick=${play}>
              ${busy ? 'Lancement…' : held ? 'Reprendre' : 'Jouer'}<${PadKey} k="✕" /></button>
            <button type="button" className="jl-secondary" data-nav="fav" aria-pressed=${String(fav)} onClick=${favourite}>
              <${Icon} name="star" filled=${fav} />${fav ? 'Retirer des favoris' : 'Ajouter aux favoris'}<${PadKey} k="△" /></button>
          </div>
        </div>
      </section>
    </div>`
  }
}
