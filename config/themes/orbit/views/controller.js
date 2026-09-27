/** The controller screen, as Orbit's accessory sheet.
 *
 * The host's markup (`sdk.defaults.GamepadView`) dressed by css/controller.css:
 * every prop passes through, so the live diagram, the mapping wizard and the
 * hold gesture stay the host's. `orbit-pad` is the class the stylesheet keys on.
 */
export function createController(sdk) {
  const {html} = sdk.ui
  return (props) => html`<${sdk.defaults.GamepadView} ...${props} skin="orbit-pad" />`
}
