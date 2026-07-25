/**
 * Skeleton theme — copy this folder, rename it, and list the surfaces you
 * implement in theme.json → "provides".
 *
 * Full contract: docs/themes/README.md
 * The app it plugs into: docs/architecture/05-frontend.md
 */
export default (sdk) => {
  const { html } = sdk.ui

  // Available surfaces (declare the ones you return, in theme.json):
  //   background · decor · home · library · topbar
  //   screensaver · keyboard · powerModal · gamepadModal
  //
  // Anything you do not return keeps the default look.
  // sdk.defaults holds the default components, so you can wrap instead of replace.

  // const Home = () => html`
  //   <div>
  //     <${sdk.defaults.DefaultHome} />
  //   </div>
  // `

  return {}
}
