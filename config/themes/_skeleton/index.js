/**
 * Skeleton theme — copy this folder, rename it, and make it yours.
 *
 * A theme is all-or-nothing: it must provide BOTH surfaces, `splash` and
 * `shell`, and list them in theme.json → "provides". Anything less does not
 * load — half a theme (a themed dashboard behind the stock boot animation) is
 * what made the first version feel broken.
 *
 * `sessionBar` below is the one exception, and the difference is worth
 * understanding before you copy it: it is OPTIONAL, it is not declared in
 * "provides", and the host draws its own if you leave it out.
 *
 * You are dressing the frontend, not rebuilding it: paging, focus, the modal
 * stack and the button bindings stay with the host, so your theme behaves
 * exactly like the default and only the UI changes.
 *
 * Keep one feature per file, like config/themes/summer, and split the way the
 * frontend splits — `views/` for what a screen looks like, `lib/` for what it
 * needs to look like that:
 *
 *     my-theme/
 *       index.js  theme.json  theme.css
 *       views/    splash.js  home.js  settings.js  …
 *       lib/      whatever your views share
 *
 * The directory listing then doubles as your check-list. Subfolders and
 * relative imports work — there is no build, so the paths you write are the
 * paths the browser fetches.
 *
 * Full contract: docs/themes/README.md
 */
export default (sdk) => {
  const { html, useEffect } = sdk.ui

  // Yours to draw, but not to skip: call onDone when finished, or the host
  // gives up waiting and boots without you.
  const Splash = ({ onDone }) => {
    useEffect(() => {
      const t = setTimeout(onDone, 1200)
      return () => clearTimeout(t)
    }, [onDone])
    return html`
      <div style=${{
        position: 'fixed', inset: 0, zIndex: 900, background: '#09090f', color: '#fff',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        font: '600 34px/1 Outfit, sans-serif', letterSpacing: '0.2em',
      }}>GAMECORE</div>`
  }

  // sdk.defaults.Shell IS the default frontend and takes views, so you rewrite
  // only what you care about:
  //   background · decor · topbar · homeView · library
  //   screensaver · settings · powerModal · gamepadModal
  //
  // Note homeView, not home: you supply the dashboard's markup, the host keeps
  // its behaviour. That is what stops a theme drifting from the default.
  //
  //   const MyHome = ({ pageItems, focusIdx }) => html`<div>…</div>`
  //   const Shell = () => html`<${sdk.defaults.Shell} homeView=${MyHome} />`
  //
  // You own one tree either way — so you own the stacking, and you never write
  // a z-index.
  const Shell = () => html`<${sdk.defaults.Shell} />`

  /**
   * The suspended-session bar — optional, and the only surface that is.
   *
   * Pressing Home twice suspends the running game instead of killing it, and
   * this is the way back to it. The host mounts a bar whether or not you
   * export one, because a theme that simply forgot would leave a frozen
   * emulator holding several gigabytes of memory with nothing on screen able
   * to resume or close it. Exporting `sessionBar` replaces the picture, never
   * the guarantee — so delete this function and the box still works, it just
   * stops looking like your theme for one bar.
   *
   * You get the state and the callbacks; the host keeps the bindings (✕
   * resumes, L1/R1 walk the list) so the gesture does not change with the
   * theme. `kind` is 'app' or 'game' — say which, or you will be offering to
   * close a "game" the player never started.
   *
   * Reading the state yourself instead: `sdk.session.use()` in a component,
   * `sdk.session.get()` in a handler, and `background()` / `resume(id)` /
   * `close(id)` to act. Touching any of those means your theme.json must
   * declare `"api": 5` — the version gate reads your sources and will refuse
   * the theme if it does not.
   *
   * No `z-index` here either: the host owns the layer this sits in.
   */
  const SessionBar = ({ sessions, focusIdx, active, busy, title, onResume, onClose }) => {
    const s = sessions[focusIdx] || sessions[0]
    if (!s) return null
    return html`
      <div style=${{
        display: 'flex', alignItems: 'center', gap: 14, padding: '12px 22px',
        background: '#12121a', borderTop: '1px solid #2a2a38', color: '#fff',
        opacity: active ? 1 : 0.75,
      }}>
        <div style=${{ flex: 1, minWidth: 0 }}>
          <div style=${{ fontSize: 10, letterSpacing: '0.14em', opacity: 0.6 }}>
            ${s.kind === 'app' ? 'APPLICATION SUSPENDED' : 'GAME SUSPENDED'}
          </div>
          <strong>${title(s)}</strong>
        </div>
        <button disabled=${busy} onClick=${() => onResume(s)}>Resume ✕</button>
        <button disabled=${busy} onClick=${() => onClose(s)}>
          Close ${s.kind === 'app' ? 'application' : 'game'}
        </button>
      </div>`
  }

  return { splash: Splash, shell: Shell, sessionBar: SessionBar }
}
