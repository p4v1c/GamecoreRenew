/**
 * The suspended session, as a card slipped under the shelf.
 *
 * Shelf's whole idea is that your library is objects on a papered wall, so a
 * frozen game is not a notification: it is the box you put down a moment ago,
 * still open, sitting on the ledge where you left it. Paper, ink, a hairline
 * rule and the seal gold — the same materials as every other surface here, and
 * nothing that glows.
 *
 * The host mounts this and owns the layer it sits in, so there is no `z-index`
 * in here and none in theme.css either. That rule is the theme system's, not a
 * preference: the shell owns stacking.
 *
 * Behaviour belongs to the host too. This file only draws: the host's session
 * bar decides what the buttons do and which keys reach them, and Shelf calls
 * nothing. That is why this theme still declares `api: 4` — it takes the state
 * as props, so a front end without the lifecycle simply never mounts the bar,
 * and the theme keeps working. Declaring 5 would take Shelf off that box
 * altogether, for a surface it does not use.
 */
export const createSessionBar = (sdk) => {
  const { html } = sdk.ui

  return ({ sessions, focusIdx, active, busy, title, onResume, onClose }) => {
    const s = sessions[focusIdx] || sessions[0]
    if (!s) return null
    const noun = s.kind === 'app' ? 'application' : 'game'

    return html`
      <aside class="cz-session" data-active=${active ? 'true' : 'false'}
             role="region" aria-label="Suspended session">
        <div class="cz-session-rule" aria-hidden="true"></div>
        <div class="cz-session-body">
          <div class="cz-session-tab">
            <span class="cz-session-mark" aria-hidden="true"></span>
            <span>PUT DOWN</span>
            ${sessions.length > 1
              ? html`<span class="cz-session-count">${focusIdx + 1} / ${sessions.length}</span>`
              : null}
          </div>
          <div class="cz-session-title">
            <strong>${title(s)}</strong>
            <small>${noun === 'app' ? 'Application' : 'Game'} · still open, not running</small>
          </div>
          <div class="cz-session-acts">
            <button class="cz-btn cz-btn-primary" disabled=${busy}
                    onClick=${() => onResume(s)}>
              ${busy ? 'One moment…' : 'Pick it back up'}<kbd>✕</kbd>
            </button>
            <button class="cz-btn" disabled=${busy} onClick=${() => onClose(s)}>
              Put the ${noun} away
            </button>
          </div>
        </div>
      </aside>`
  }
}
