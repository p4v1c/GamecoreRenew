/**
 * Skeleton theme — copy this folder, rename it, and list the surfaces you
 * implement in theme.json → "provides".
 *
 * Full contract: docs/themes/README.md
 * The app it plugs into: docs/architecture/05-frontend.md
 */
export default (sdk) => {
  const { html } = sdk.ui

  // A theme provides one thing: the shell — the whole frontend body.
  //
  // sdk.defaults.Shell IS the default frontend and takes parts, so you only
  // rewrite what you care about:
  //   background · decor · topbar · home · library
  //   screensaver · settings · powerModal · gamepadModal
  //
  // const MyHome = () => html`<div>…</div>`
  // return { shell: () => html`<${sdk.defaults.Shell} home=${MyHome} />` }
  //
  // Or return your own tree entirely and pick from sdk.defaults what you do
  // not want to write. Either way you own one tree — so you own the stacking,
  // and you never write a z-index.

  return { shell: () => html`<${sdk.defaults.Shell} />` }
}
