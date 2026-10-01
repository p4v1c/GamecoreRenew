import {duration, lastPlayed} from '../lib/format.js'
import {systemName, systemYear} from '../lib/catalog.js'
import {isFavourite, toggleFavourite, createUseFavourites} from '../lib/favourites.js'
import {createSpatial, layerOwnsPad} from '../lib/spatial.js'

/** Raise the modal depth for as long as a layer is up; the depth it lands on
 * is how its handlers tell that nothing has opened on top of it since. */
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

/** A game's card, opened from anywhere a game is shown.
 *
 * Play launches through the host (`sdk.defaults.launchGame`, or the library's
 * own `onLaunch` there), and a game already frozen in the background is
 * resumed instead of started twice. The fiche stays up until the launch
 * resolves, so a refusal is said here rather than lost.
 */
export function createDetails(sdk, cards) {
  const {html, useState, useEffect, useRef} = sdk.ui
  const PadKey = sdk.ui.PadKey || (({k}) => html`<kbd>${k}</kbd>`)
  const useSpatial = createSpatial(sdk)
  const useLayer = createUseLayer(sdk)
  const useFavourites = createUseFavourites(sdk)

  return function Details({game, onClose, onPlay}) {
    const root = useRef(null)
    const depth = useLayer()
    const [meta, setMeta] = useState(null)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    const {background} = sdk.session.use()
    useFavourites()
    const held = cards.heldGame(background, game)
    const fav = isFavourite(game.systemId, game.gameKey)

    useEffect(() => {
      let alive = true
      sdk.api.metadata.get(game.systemId, game.gameKey)
        .then((m) => { if (alive && m?.found) setMeta(m) })
        .catch(() => { /* no metadata is a shorter card, not an error */ })
      return () => { alive = false }
    }, [game.key])

    const play = async () => {
      if (busy) return
      setBusy(true)
      setError('')
      try {
        if (held) await sdk.session.resume(held.session)
        else if (onPlay) await onPlay(game)
        else await sdk.defaults.launchGame({systemId: game.systemId, path: game.path, gameKey: game.gameKey})
        onClose()
      } catch (e) {
        setError(e?.message || 'Le jeu n’a pas pu démarrer.')
        setBusy(false)
      }
    }

    useSpatial(root, {
      allowed: () => layerOwnsPad(sdk, depth.current),
      initial: '[data-nav="play"]',
      keys: {back: onClose, y: () => toggleFavourite(game.systemId, game.gameKey)},
    })

    const facts = [
      ['Console', systemName(game.system)],
      meta?.year || systemYear(game.system) ? ['Année', meta?.year || systemYear(game.system)] : null,
      meta?.developer ? ['Studio', meta.developer] : null,
      Array.isArray(meta?.genres) && meta.genres.length ? ['Genre', meta.genres.slice(0, 3).join(', ')] : null,
      meta?.players ? ['Joueurs', meta.players_label || String(meta.players)] : null,
      ['Temps de jeu', duration(game.seconds)],
      game.lastPlayed ? ['Dernière partie', lastPlayed(game.lastPlayed)] : null,
    ].filter(Boolean)

    return html`<div className="jl-scrim" onClick=${(e) => { if (e.target === e.currentTarget) onClose() }}>
      <section className="jl-dialog jl-details" ref=${root} role="dialog" aria-modal="true"
               aria-labelledby="jl-details-title">
        <button type="button" className="jl-close" data-nav="close" aria-label="Fermer la fiche"
                onClick=${onClose}>×</button>
        <div className="jl-details-art"><${cards.Cover} game=${game} big=${true} /></div>
        <div className="jl-details-copy">
          <span className="jl-eyebrow">${systemName(game.system)}${held ? ' · en pause' : ''}</span>
          <h2 id="jl-details-title">${meta?.title || game.title}</h2>
          <p className="jl-details-text">${meta?.description || 'Pas encore de description pour ce jeu.'}</p>
          <dl className="jl-facts">${facts.map(([k, v]) => html`<div key=${k}><dt>${k}</dt><dd>${v}</dd></div>`)}</dl>
          ${error ? html`<p className="jl-error" role="alert">${error}</p>` : null}
          <div className="jl-actions">
            <button type="button" className="jl-play" data-nav="play" disabled=${busy} onClick=${play}>
              ${busy ? 'Lancement…' : held ? 'Reprendre' : 'Jouer'}<${PadKey} k="✕" /></button>
            <button type="button" className="jl-secondary" data-nav="fav" aria-pressed=${String(fav)}
                    onClick=${() => toggleFavourite(game.systemId, game.gameKey)}>
              ${fav ? '★ Retirer des favoris' : '☆ Ajouter aux favoris'}<${PadKey} k="△" /></button>
          </div>
        </div>
      </section>
    </div>`
  }
}
