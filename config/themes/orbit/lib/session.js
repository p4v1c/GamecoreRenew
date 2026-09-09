import {consoles, coverUrl} from './catalog.js'

/** Orbit's session surface, over the real backend.
 *
 * This was a pure in-memory model — `foreground`, `background`, `askClose` and
 * a `session` object that no process ever answered to. It drew the feature
 * convincingly and suspended nothing, and its own README said so. What replaced
 * it is `sdk.session` (SDK 5): the state comes from the box and the actions
 * reach ProcessManager, which signals the process GROUP so a Flatpak sandbox
 * freezes down to the last of its five processes.
 *
 * Nothing here decides anything about lifecycle. Which sessions may exist, how
 * many, and what happens when one is resumed while another holds the screen are
 * the core's rules — a theme making its own would be a second answer to a
 * question that has to have one.
 */
export function createSession(sdk) {
  const {html, useState, useEffect, useRef} = sdk.ui

  /** Real artwork or initials — never a stand-in dressed as a cover. */
  function Image({src, alt = '', className = ''}) {
    const [failed, setFailed] = useState(false)
    return src && !failed
      ? html`<img className=${className} src=${src} alt=${alt} draggable="false"
                  onError=${() => setFailed(true)} />`
      : html`<span className="art-fallback">${(alt || '◇').slice(0, 2).toUpperCase()}</span>`
  }

  /** Orbit may open its own surface only when nothing the core owns is up. */
  const available = () => {
    const s = sdk.nav.get()
    return !s.modalDepth && !s.sessionGameKey && !s.powerPending && s.standby === 'off'
  }

  const noun = (s) => (s?.kind === 'app' ? 'application' : 'game')
  const titleOf = (s) => (s?.kind === 'app'
    ? (s.systemId || s.gameKey)
    : sdk.format.gameName(s?.gameKey || ''))

  /** Real artwork or none at all — never a stand-in dressed as a cover.
   *
   * A game's `gameKey` IS its ROM filename (routers/games.py), so the cover
   * endpoint takes it directly. An application has no cover; it falls back to
   * the console photo Orbit owns for that pack, and then to `Image`'s initials.
   */
  const artOf = (s) => {
    if (!s) return null
    if (s.kind === 'app') {
      const asset = consoles[s.systemId]?.[0]
      return asset ? sdk.system.asset(`assets/consoles/${asset}`) : null
    }
    return s.systemId && s.gameKey ? coverUrl(s.systemId, s.gameKey) : null
  }

  /** Is this library row or app tile the thing that is suspended? */
  const heldMatch = (held, gameKey, systemId) =>
    held.find((s) => s.gameKey === gameKey && s.systemId === systemId) || null

  // ── the menu, drawn by the host ───────────────────────────────────────────

  /** Orbit's session menu. The host opens it on L2, owns its navigation and
   *  its modal lock, and hands it the actions already resolved — so this is
   *  markup, the same bargain as the bar.
   *
   *  Orbit used to bind L2 and drive its own panel. That was one theme solving
   *  a problem every theme had, and it collided the moment the host grew the
   *  same binding: two panels, one press. */
  function Menu({session, sessions, index, confirming, busy, actions, actionIdx, title}) {
    return html`<section className="session-menu-body" role="dialog" aria-modal="true"
                         aria-labelledby="orbit-session-title">
      <span className="eyebrow">${confirming ? 'END THIS SESSION' : 'SUSPENDED SESSION'}${
        sessions.length > 1 ? ` · ${index + 1} / ${sessions.length}` : ''}</span>
      <div className="session-menu-header">
        <${Image} src=${artOf(session)} alt=${title(session)} />
        <div><p>${session.kind === 'app' ? 'Application' : 'Game'}${
          session.systemId ? ` · ${session.systemId}` : ''}</p>
          <h1 id="orbit-session-title">${title(session)}</h1></div>
      </div>
      <p>${confirming
        ? `This ends the ${noun(session)}. Anything it has not saved is lost.`
        : 'Frozen exactly where you left it. Nothing is running, and no playtime is counting.'}</p>
      <div className="session-menu-scene" aria-hidden="true"><span className="session-orb" />
        <span>${confirming ? 'This cannot be undone.' : 'Ready when you are.'}</span></div>
      <div className="session-menu-options">
        ${actions.map((action, i) => html`<button key=${action.id} disabled=${busy}
          data-active=${actionIdx === i ? 'true' : 'false'}
          className=${`session-menu-option ${action.primary ? 'recommended' : ''} ${
            action.danger ? 'session-danger' : ''}`}
          onClick=${action.run}>${busy ? 'Working…' : action.label}</button>`)}
      </div>
      <p className="session-menu-hints">↑ ↓ Choose · ✕ Confirm · ○ Back${
        sessions.length > 1 ? ' · L1 R1 Session' : ''}</p>
    </section>`
  }

  // ── the bar, mounted by the host above the shell ──────────────────────────

  /** Orbit's dock — the mockup's `#session-dock`, drawn by the host.
   *
   * The host mounts it and guarantees it is on screen: a theme replaces the
   * picture, never the way back to a suspended game. Class names are the
   * mockup's so the design in theme.css applies unchanged.
   *
   * The hint names L2 in BOTH states, and that is the correction. The bar owns
   * no button at all — the host took ✕ away from it on purpose, because the
   * screen underneath takes ✕ too and one press resumed the session *and*
   * opened whatever tile the cursor was on. This dock went on advertising
   * "✕ Resume · ○ Back" anyway, and `active` is exactly when it is shown: so
   * the moment the bar became usable, Orbit hid the one binding that works and
   * offered two that do nothing. The player presses ✕, nothing happens, and
   * there is nothing on screen left to try. Shelf's ledge says L2 and works.
   */
  function Bar({sessions, focusIdx, active, busy, onResume, onClose}) {
    const s = sessions[focusIdx] || sessions[0]
    if (!s) return null
    return html`<aside className=${`session-dock ${active ? 'controller-active' : ''}`}
                       aria-label="Background session">
      <div className="session-dock-art"><${Image} src=${artOf(s)} alt=${titleOf(s)} /></div>
      <div className="session-dock-info">
        <span><i className="status-light" /> IN BACKGROUND${
          sessions.length > 1 ? ` · ${focusIdx + 1}/${sessions.length}` : ''}</span>
        <strong>${titleOf(s)}</strong>
        <small>${s.kind === 'app' ? 'Application' : 'Game'} · <span
          className="session-dock-idle-hint">L2 to manage</span><span
          className="session-dock-active-hint">L2 to resume or close</span></small>
      </div>
      <div className="session-dock-actions">
        <button className="primary-button" disabled=${busy}
                onClick=${() => onResume(s)}>${busy ? 'Working…' : 'Resume'}</button>
        <button className="session-dock-more" disabled=${busy}
                onClick=${() => onClose(s)}
                aria-label=${`Close ${titleOf(s)} permanently`}>
          <span>Close ${noun(s)}</span></button>
      </div>
      <kbd className="session-dock-shortcut">L2</kbd>
    </aside>`
  }

  return {available, heldMatch, titleOf, noun, artOf, Bar, Menu}
}
