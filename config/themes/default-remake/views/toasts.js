/**
 * The notification stack.
 *
 * This surface is the reason `toasts` became a part. It used to be rendered by
 * the shell and was not overridable, so a theme that wrote its own tree lost
 * every notification there is: the ROM that finished uploading, the pad that
 * went flat, the game that did not start, and the offer to map a controller
 * emulators cannot bind.
 *
 * The queue is not here and cannot be. Which events become a toast, how long
 * each stays, and which ones go to Electron's native always-on-top HUD instead
 * are all the host's — a themed stack that could choose might quietly drop the
 * one toast whose whole point is that the player acts on it.
 *
 * Two details are load-bearing and both are easy to lose in a rewrite:
 * the stack is click-through so a toast never steals a press from the screen
 * behind it, and a toast carrying an action has to take that back or its button
 * is decoration. `onDismiss` after running the action, or the offer stays on
 * screen having already been accepted.
 */
export const createToasts = (sdk) => {
  const { html, motion, AnimatePresence } = sdk.ui

  return ({ toasts, onDismiss }) => html`
    <div class="dr-toasts">
      <${AnimatePresence}>
        ${toasts.map(t => html`
          <${motion.div} key=${t.id}
            initial=${{ opacity: 0, x: 60, scale: 0.95 }}
            animate=${{ opacity: 1, x: 0, scale: 1 }}
            exit=${{ opacity: 0, x: 60, scale: 0.95 }}
            transition=${{ type: 'spring', stiffness: 400, damping: 30 }}
            class="dr-toast"
            style=${{
              border: `1px solid ${t.accent}40`,
              boxShadow: `0 8px 32px rgba(0,0,0,0.5), 0 0 12px ${t.accent}20`,
              pointerEvents: t.action ? 'auto' : 'none',
            }}>
            <div class="dr-toast-icon" style=${{ background: `${t.accent}20` }}>${t.icon}</div>
            <div class="dr-toast-body">
              <div class="dr-toast-title" style=${{ color: t.accent }}>${t.title}</div>
              <div class="dr-toast-text">${t.body}</div>
              ${t.action ? html`
                <button class="dr-toast-btn"
                        style=${{ background: `${t.accent}22`, borderColor: `${t.accent}66`, color: t.accent }}
                        onClick=${() => { t.action.run(); onDismiss(t.id) }}>
                  ${t.action.label}
                </button>` : null}
            </div>
          <//>`)}
      <//>
    </div>`
}
