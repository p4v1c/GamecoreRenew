import {consoles, coverUrl} from './artwork.js'

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
export function createSession(sdk, artwork) {
  const {html, useState, useEffect, useRef} = sdk.ui
  const {Image} = artwork

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

  // ── the panel, opened with L2 ─────────────────────────────────────────────

  const openListeners = new Set()
  const openPanel = () => openListeners.forEach((fn) => fn())

  function Panel() {
    const {background} = sdk.session.use()
    const [open, setOpen] = useState(false)
    const [pick, setPick] = useState(0)      // which suspended session
    const [idx, setIdx] = useState(0)        // which button
    const [confirm, setConfirm] = useState(false)
    const [busy, setBusy] = useState(false)
    const buttons = useRef([])
    const restoreTo = useRef(null)
    const live = useRef({})

    const close = () => {setOpen(false); setConfirm(false)}

    useEffect(() => {
      const fn = () => {setOpen(true); setPick(0); setIdx(0); setConfirm(false)}
      openListeners.add(fn)
      return () => openListeners.delete(fn)
    }, [])

    // Nothing suspended any more — closed from the bar, or killed from under us.
    useEffect(() => {if (!background.length) close()}, [background.length])

    const session = background[Math.min(pick, Math.max(0, background.length - 1))] || null

    const run = async (fn) => {
      if (live.current.busy) return
      setBusy(true)
      try {
        await fn()
        close()
      } catch (e) {
        // The core owns the rules; if it refused, it had a reason. Pretending
        // the action worked would be worse than saying nothing.
        console.warn('[orbit] session action refused:', e)
      } finally {
        setBusy(false)
      }
    }

    const actions = !session ? []
      : confirm
        ? [{key: 'keep', label: 'Keep it running', run: () => setConfirm(false)},
           {key: 'close', label: `Close ${noun(session)}`, danger: true,
            run: () => run(() => sdk.session.close(session.session))}]
        : [{key: 'resume', label: `Resume ${noun(session)}`, primary: true,
            run: () => run(() => sdk.session.resume(session.session))},
           {key: 'ask', label: `Close ${noun(session)}…`, run: () => setConfirm(true)},
           {key: 'back', label: 'Back to collection', run: close}]

    live.current = {actions, idx, confirm, busy, count: background.length}

    useEffect(() => setIdx(0), [confirm, pick])

    /* Focus follows the cursor, and is HANDED BACK on the way out. A modal that
       takes DOM focus and closes without returning it leaves the document
       focused on a node that no longer exists: harmless for the pad, which is
       event-driven, and not harmless for anyone reviewing the theme with a
       keyboard, who lands back at the top of the page. */
    useEffect(() => {
      if (!open) return
      restoreTo.current = document.activeElement
      return () => {
        const back = restoreTo.current
        if (back && back.isConnected && typeof back.focus === 'function') {
          back.focus({preventScroll: true})
        }
      }
    }, [open])

    useEffect(() => {
      if (open) buttons.current[idx]?.focus({preventScroll: true})
    }, [open, idx, confirm, pick])

    useEffect(() => {
      if (!open) return
      sdk.nav.openModal()
      const owned = sdk.nav.get().modalDepth
      // Ours only while it is the top modal and nothing the core owns is up,
      // otherwise both sets of handlers fire on the same press.
      const mine = () => {
        const s = sdk.nav.get()
        return s.modalDepth === owned && !s.sessionGameKey && !s.powerPending
          && s.standby === 'off'
      }
      const move = (d) => {
        if (!mine()) return
        const n = live.current.actions.length
        if (n) setIdx((i) => (i + d + n) % n)
      }
      const walk = (d) => {
        if (!mine() || live.current.count < 2) return
        setConfirm(false)
        setPick((p) => (p + d + live.current.count) % live.current.count)
      }
      const back = () => {
        if (!mine()) return
        if (live.current.confirm) setConfirm(false)
        else close()
      }
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => move(-1)),
        sdk.input.onGp('gp:dpad-left', () => move(-1)),
        sdk.input.onGp('gp:dpad-down', () => move(1)),
        sdk.input.onGp('gp:dpad-right', () => move(1)),
        sdk.input.onGp('gp:confirm', () => {
          if (mine()) live.current.actions[live.current.idx]?.run()
        }),
        sdk.input.onGp('gp:back', back),
        sdk.input.onGp('gp:l2', back),
        // L1/R1 walk between suspended sessions — the same keys the host's own
        // bar uses, so the gesture does not change with the theme.
        sdk.input.onGp('gp:l1', () => walk(-1)),
        sdk.input.onGp('gp:r1', () => walk(1)),
      ]
      return () => {offs.forEach((off) => off()); sdk.nav.closeModal()}
    }, [open])

    if (!open || !session) return null
    return html`<${sdk.defaults.SettingsOverlay} onClose=${close} width=${880}>
      <section className="orbit-session-panel" role="dialog" aria-modal="true"
               aria-labelledby="orbit-session-title">
        <span className="orbit-eyebrow">${confirm ? 'CLOSE THIS SESSION' : 'SUSPENDED SESSION'}${
          background.length > 1 ? ` · ${pick + 1} / ${background.length}` : ''}</span>
        <div className="orbit-session-identity">
          <${Image} src=${artOf(session)} alt=${titleOf(session)} />
          <div>
            <p>${session.kind === 'app' ? 'Application' : 'Game'}${
              session.systemId ? ` · ${session.systemId}` : ''}</p>
            <h1 id="orbit-session-title">${confirm
              ? `Close ${titleOf(session)}?` : titleOf(session)}</h1>
          </div>
        </div>
        <p>${confirm
          ? `This ends the ${noun(session)}. Anything it has not saved is lost.`
          : 'Frozen exactly where you left it. Nothing is running, and no playtime is counting.'}</p>
        <div className="orbit-session-scene" aria-hidden="true">
          <span className="orbit-orb" />
          <span>${confirm ? 'This cannot be undone.' : 'Ready when you are.'}</span>
        </div>
        <div className="orbit-actions">${actions.map((action, i) => html`<button
          key=${action.key} ref=${(el) => {buttons.current[i] = el}}
          data-active=${idx === i ? 'true' : 'false'} disabled=${busy}
          className=${`orbit-button ${action.primary ? 'orbit-primary' : ''} ${action.danger ? 'orbit-danger' : ''}`}
          onFocus=${() => setIdx(i)} onClick=${action.run}>${
            busy ? 'Working…' : action.label}</button>`)}</div>
        <p className="orbit-muted">Directional pad · ✕ select · ○ / L2 back${
          background.length > 1 ? ' · L1 R1 switch session' : ''}</p>
      </section>
    <//>`
  }

  // ── the bar, mounted by the host above the shell ──────────────────────────

  /** Orbit's dock. The host mounts this and guarantees it is on screen: a theme
   *  replaces the picture, never the way back to a suspended game. */
  function Bar({sessions, focusIdx, active, busy, onResume, onClose}) {
    const s = sessions[focusIdx] || sessions[0]
    if (!s) return null
    return html`<div className="orbit-session-dock" data-active=${active ? 'true' : 'false'}
                     role="region" aria-label="Suspended session">
      <span className="orbit-dock-orb" aria-hidden="true" />
      <${Image} className="orbit-dock-art" src=${artOf(s)} alt=${titleOf(s)} />
      <div className="orbit-dock-text">
        <span className="orbit-eyebrow">${s.kind === 'app'
          ? 'APPLICATION SUSPENDED' : 'GAME SUSPENDED'}${
          sessions.length > 1 ? ` · ${focusIdx + 1}/${sessions.length}` : ''}</span>
        <strong>${titleOf(s)}</strong>
      </div>
      <button className="orbit-button orbit-primary" disabled=${busy}
              onClick=${() => onResume(s)}>${busy ? 'Working…' : 'Resume'} <kbd>✕</kbd></button>
      <button className="orbit-button" disabled=${busy}
              onClick=${() => onClose(s)}>Close ${noun(s)}</button>
      <kbd className="orbit-dock-key">L2</kbd>
    </div>`
  }

  /** L2 anywhere: manage whatever is suspended. Bound once, by the shell. */
  function useSessionShortcut() {
    useEffect(() => sdk.input.onGp('gp:l2', () => {
      if (available() && sdk.session.get().background.length) openPanel()
    }), [])
  }

  return {available, heldMatch, titleOf, noun, artOf, Bar, Panel, useSessionShortcut}
}
