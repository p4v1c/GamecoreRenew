import {coverUrl, titleFromKey} from '../lib/catalog.js'

/** The bar over a suspended game and the menu PS ×2 opens: markup only. The
 * host mounts both, holds the pad and resolves the actions (SDK 5). */
export function createSession(sdk, {Icon}) {
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
    return html`<aside className="jl-dock" aria-label="Paused game">
      <span className="jl-dock-art"><${Art} s=${s} /></span>
      <span className="jl-dock-text"><small><${Icon} name="pause" />Paused${sessions.length > 1 ? `, ${focusIdx + 1} of ${sessions.length}` : ''}</small>
        <b>${titleOf(s)}</b></span>
      <button type="button" className="jl-dock-button" disabled=${busy} onClick=${() => onManage?.()}>
        ${busy ? 'One moment…' : 'Manage'}</button>
      <span className="jl-dock-key"><${PadKey} k="PS ×2" /></span>
    </aside>`
  }

  /** Actions arrive resolved, with the pad already bound by the host. */
  function Menu({session, sessions, index, confirming, busy, actions, actionIdx, title}) {
    const noun = session.kind === 'app' ? 'the app' : 'the game'
    return html`<section className="jl-session" role="dialog" aria-modal="true" aria-labelledby="jl-session-title">
      <div className="jl-session-art"><${Art} s=${session} /></div>
      <div className="jl-session-copy">
        <span className="jl-eyebrow">${confirming ? 'Close it for real?' : session.kind === 'app' ? 'App paused' : 'Game paused'}${
          sessions.length > 1 ? `, ${index + 1} of ${sessions.length}` : ''}</span>
        <h2 id="jl-session-title">${title(session)}</h2>
        <p>${confirming
          ? `Closing ${noun} loses anything not saved.`
          : 'Frozen exactly where you left it. Nothing runs, and playtime isn’t counted.'}</p>
        <div className="jl-session-actions">
          ${actions.map((a, i) => html`<button type="button" key=${a.id} disabled=${busy}
            data-active=${actionIdx === i ? 'true' : 'false'}
            className=${`jl-session-option ${a.primary ? 'is-primary' : ''} ${a.danger ? 'is-danger' : ''}`}
            onClick=${a.run}>${busy ? 'One moment…' : a.label}</button>`)}
        </div>
        <p className="jl-session-hints"><${PadHints} text=${'↑ ↓ Choose · ✕ Confirm · ○ Back'
          + (sessions.length > 1 ? ' · L1 R1 Session' : '')} /></p>
      </div>
    </section>`
  }

  return {Bar, Menu}
}
