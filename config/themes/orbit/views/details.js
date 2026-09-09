import {coverUrl, systemName, isFavourite, toggleFavourite} from '../lib/catalog.js'

export function createDetails(sdk) {
  const {html, useEffect, useRef, useState} = sdk.ui
  return function Details({game, onClose, onPlay}) {
    const root = useRef(null)
    const [meta, setMeta] = useState(null)
    const [fav, setFav] = useState(() => isFavourite(game.systemId, game.gameKey))
    const [art, setArt] = useState(coverUrl(game.systemId, game.gameKey))
    const [failed, setFailed] = useState(false)
    const live = useRef({onClose, onPlay})
    live.current = {onClose, onPlay}
    useEffect(() => {
      const previous = document.activeElement
      sdk.nav.openModal()
      root.current?.querySelector('.primary-button')?.focus()
      const offs = [sdk.input.onGp('gp:back', () => live.current.onClose()),
        sdk.input.onGp('gp:confirm', () => document.activeElement?.click()),
        ...['left', 'right', 'up', 'down'].map((direction, i) => sdk.input.onGp(`gp:dpad-${direction}`, () => {
          const buttons = [...root.current.querySelectorAll('button:not(:disabled)')]
          const at = buttons.indexOf(document.activeElement)
          buttons[(at + (i % 2 ? 1 : -1) + buttons.length) % buttons.length]?.focus()
        }))]
      return () => { offs.forEach(off => off()); sdk.nav.closeModal(); previous?.focus?.() }
    }, [])
    useEffect(() => {
      let live = true
      sdk.api.metadata.get(game.systemId, game.gameKey).then(m => { if (live && m?.found) setMeta(m) }).catch(() => {})
      sdk.api.media.list(game.systemId, game.gameKey).then(index => {
        if (!live) return
        const type = ['fanart-background', 'background', 'screenshot-gameplay'].find(t => index?.media?.[t]?.kind === 'image')
        if (type) setArt(sdk.api.media.url(game.systemId, game.gameKey, type))
      }).catch(() => {})
      return () => { live = false }
    }, [game.systemId, game.gameKey])
    return html`<div className="orbit-dialog-backdrop" onClick=${e => { if (e.target === e.currentTarget) onClose() }}>
      <section ref=${root} role="dialog" aria-modal="true" aria-labelledby="details-title" className="glass-dialog orbit-details">
        <button className="close-dialog icon-button" aria-label="Close game details" onClick=${onClose}>×</button>
        ${!failed ? html`<img className="details-art" src=${art} alt="" onError=${() => {
          const fallback = coverUrl(game.systemId, game.gameKey)
          if (art !== fallback) setArt(fallback)
          else setFailed(true)
        }} />` : null}
        <p className="eyebrow">${systemName(game.system)} ${meta?.year ? `· ${meta.year}` : ''}</p>
        <h2 id="details-title">${meta?.title || game.title}</h2>
        <p className="dialog-description">${meta?.description || 'No description available for this game.'}</p>
        <dl className="details-grid">
          ${meta?.developer ? html`<div><dt>Studio</dt><dd>${meta.developer}</dd></div>` : null}
          ${Array.isArray(meta?.genres) && meta.genres.length ? html`<div><dt>Genre</dt><dd>${meta.genres.join(' · ')}</dd></div>` : null}
          <div><dt>Emulator</dt><dd>${game.system?.label || game.systemId}</dd></div>
          <div><dt>Console</dt><dd>${systemName(game.system)}</dd></div>
          ${meta?.players ? html`<div><dt>Players</dt><dd>${meta.players_label || meta.players}</dd></div>` : null}
        </dl>
        <div className="hero-actions"><button className="primary-button" onClick=${() => {onClose(); onPlay()}}>▶ Play</button>
          <button className="round-button" aria-label="Favourite" aria-pressed=${String(fav)}
            onClick=${() => setFav(toggleFavourite(game.systemId, game.gameKey))}>${fav ? '♥' : '♡'}</button></div>
      </section>
    </div>`
  }
}
