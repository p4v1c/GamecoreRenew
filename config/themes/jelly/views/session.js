import {coverUrl, titleFromKey} from '../lib/catalog.js'

/** The suspended session: the bar over a frozen game and the menu PS ×2 opens.
 *
 * Both are markup over the host's lifecycle (`sessionBar` / `sessionMenu`,
 * SDK 5). The host mounts the bar, opens the menu, holds its pad and resolves
 * the actions; nothing here suspends, resumes or closes anything by itself.
 */
export function createSession(sdk) {
  const {html, useState} = sdk.ui
  const PadKey = sdk.ui.PadKey || (({k}) => html`<kbd>${k}</kbd>`)
  const PadHints = sdk.ui.PadHints || (({text}) => text)

  const titleOf = (s) => (s?.kind === 'app' ? (s.systemId || s.gameKey) : titleFromKey(sdk, s?.gameKey))
  const artOf = (s) => (s?.kind === 'app'
    // The logo route matches a pack id as a file name: an app's own logo.
    ? (s.systemId ? `/assets/logos/${encodeURIComponent(s.systemId)}.png` : null)
    : s?.systemId && s?.gameKey ? coverUrl(s.systemId, s.gameKey) : null)

  function Art({s}) {
    const [failed, setFailed] = useState(false)
    const src = artOf(s)
    return src && !failed
      ? html`<img src=${src} alt="" draggable="false" onError=${() => setFailed(true)} />`
      : html`<span className="jl-picture-mark">${String(titleOf(s) || '?').slice(0, 2).toUpperCase()}</span>`
  }

  /** The bar takes no button: the screen under it owns ✕. It points at PS ×2. */
  function Bar({sessions, focusIdx, busy, onManage}) {
    const s = sessions[focusIdx] || sessions[0]
    if (!s) return null
    return html`<aside className="jl-dock" aria-label="Partie en pause">
      <span className="jl-dock-art"><${Art} s=${s} /></span>
      <span className="jl-dock-text"><small>❚❚ En pause${sessions.length > 1 ? ` · ${focusIdx + 1}/${sessions.length}` : ''}</small>
        <b>${titleOf(s)}</b></span>
      <button type="button" className="jl-dock-button" disabled=${busy} onClick=${() => onManage?.()}>
        ${busy ? 'Un instant…' : 'Gérer'}</button>
      <span className="jl-dock-key"><${PadKey} k="PS ×2" /></span>
    </aside>`
  }

  /** Actions arrive resolved, with the pad already bound by the host. */
  function Menu({session, sessions, index, confirming, busy, actions, actionIdx, title}) {
    const noun = session.kind === 'app' ? 'l’application' : 'la partie'
    return html`<section className="jl-session" role="dialog" aria-modal="true" aria-labelledby="jl-session-title">
      <div className="jl-session-art"><${Art} s=${session} /></div>
      <div className="jl-session-copy">
        <span className="jl-eyebrow">${confirming ? 'On arrête vraiment ?' : session.kind === 'app' ? 'Application en pause' : 'Partie en pause'}${
          sessions.length > 1 ? ` · ${index + 1} sur ${sessions.length}` : ''}</span>
        <h2 id="jl-session-title">${title(session)}</h2>
        <p>${confirming
          ? `Fermer ${noun} perd tout ce qui n’a pas été sauvegardé.`
          : 'Figée exactement là où tu l’as laissée. Rien ne tourne, le temps de jeu ne compte pas.'}</p>
        <div className="jl-session-actions">
          ${actions.map((a, i) => html`<button type="button" key=${a.id} disabled=${busy}
            data-active=${actionIdx === i ? 'true' : 'false'}
            className=${`jl-session-option ${a.primary ? 'is-primary' : ''} ${a.danger ? 'is-danger' : ''}`}
            onClick=${a.run}>${busy ? 'Un instant…' : a.label}</button>`)}
        </div>
        <p className="jl-session-hints"><${PadHints} text=${'↑ ↓ Choisir · ✕ Valider · ○ Retour'
          + (sessions.length > 1 ? ' · L1 R1 Session' : '')} /></p>
      </div>
    </section>`
  }

  return {Bar, Menu}
}
