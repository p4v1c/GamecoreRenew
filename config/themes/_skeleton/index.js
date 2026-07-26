/**
 * Skeleton theme — copy this folder, rename it, and make it yours.
 *
 * A theme is all-or-nothing: it must provide BOTH surfaces, `splash` and
 * `shell`, and list them in theme.json → "provides". Anything less does not
 * load — half a theme (a themed dashboard behind the stock boot animation) is
 * what made the first version feel broken.
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

  return { splash: Splash, shell: Shell }
}
