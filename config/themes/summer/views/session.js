/**
 * The suspended session, as a pane of sea glass on the tideline.
 *
 * Summer is glass over a moving ocean, so a frozen game is drawn the way
 * everything else here is: a translucent panel with a hairline, floating over
 * the water rather than sitting on a surface. The one thing that does not move
 * is the point — the ocean behind it is still animating, and the session is
 * not. Mandarin marks the thing ✕ will act on, the same accent the rest of the
 * theme uses for "this one".
 *
 * The host mounts this and owns the layer it sits in, so there is no `z-index`
 * here. Behaviour is the host's too: this file only draws, and calls nothing.
 * That is why Summer still declares `api: 4` — it takes the state as props, so
 * a front end without the lifecycle never mounts the bar and the theme keeps
 * working. Declaring 5 would take Summer off that box for a surface it does
 * not use.
 */
export const createSessionBar = (sdk) => {
  const { html } = sdk.ui

  return ({ sessions, focusIdx, active, busy, title, onResume, onClose }) => {
    const s = sessions[focusIdx] || sessions[0]
    if (!s) return null
    const app = s.kind === 'app'

    return html`
      <aside class="sm-session" data-active=${active ? 'true' : 'false'}
             role="region" aria-label="Suspended session">
        <span class="sm-session-buoy" aria-hidden="true"></span>
        <div class="sm-session-text">
          <span class="sm-session-label">
            ${app ? 'APPLICATION ON HOLD' : 'GAME ON HOLD'}
            ${sessions.length > 1
              ? html`<i>${focusIdx + 1}/${sessions.length}</i>`
              : null}
          </span>
          <strong>${title(s)}</strong>
        </div>
        <div class="sm-session-acts">
          <button class="sm-session-btn sm-session-go" disabled=${busy}
                  onClick=${() => onResume(s)}>
            ${busy ? 'One moment…' : 'Dive back in'}</button>
          <button class="sm-session-btn" disabled=${busy} onClick=${() => onClose(s)}>
            Let ${app ? 'the app' : 'it'} go
          </button>
          <kbd class="sm-session-key">L2</kbd>
        </div>
      </aside>`
  }
}

/**
 * The menu the tideline opens, on L2.
 *
 * The bar alone could only be used with a pointer: ✕ belongs to the screen
 * underneath, so Resume had no key and Close had no route. The host opens this
 * instead — a real modal, so everything else stands down — and Summer draws it
 * as another pane of sea glass, held still over the water.
 */
export const createSessionMenu = (sdk) => {
  const { html } = sdk.ui

  return ({ session, sessions, index, confirming, busy, actions, actionIdx, title }) => html`
    <section class="sm-session-panel" role="dialog" aria-modal="true">
      <p class="sm-session-panel-label">
        ${confirming ? 'LETTING IT GO' : 'ON HOLD'}
        ${sessions.length > 1 ? html`<i>${index + 1}/${sessions.length}</i>` : null}
      </p>
      <h2>${title(session)}</h2>
      <p class="sm-session-panel-note">
        ${confirming
          ? `This ends the ${session.kind === 'app' ? 'app' : 'game'}. Anything it has not saved goes with it.`
          : 'Held exactly where you left it. Nothing is running, and no time is counting.'}
      </p>
      <div class="sm-session-panel-actions">
        ${actions.map((action, i) => html`
          <button key=${action.id} disabled=${busy}
                  class=${`sm-session-btn ${action.primary ? 'sm-session-go' : ''} ${action.danger ? 'sm-session-danger' : ''}`}
                  data-active=${actionIdx === i ? 'true' : 'false'}
                  onClick=${action.run}>${busy ? 'One moment…' : action.label}</button>`)}
      </div>
      <p class="sm-session-panel-hints">↑ ↓ Choose · ✕ Confirm · ○ Back${
        sessions.length > 1 ? ' · L1 R1 Session' : ''}</p>
    </section>`
}
