/** The controller screen: the host's markup (`sdk.defaults.GamepadView`),
 * every prop passed through so the live diagram, the mapping wizard and the
 * double-□ close stay the host's. css/settings.css dresses it (`jelly-pad`). */
export function createController(sdk) {
  const {html} = sdk.ui
  return (props) => html`<${sdk.defaults.GamepadView} ...${props} skin="jelly-pad" />`
}
