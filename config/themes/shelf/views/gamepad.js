/**
 * The controller screen, as an ivory paper sheet with warm line art.
 *
 * The host's markup (`sdk.defaults.GamepadView`) dressed by css/controller.css.
 * Every prop passes through, so the diagram, the wizard and the hold gesture
 * stay the host's.
 * Props: frontend/src/components/modals/gamepad/types.ts
 */
export const createGamepadView = (sdk) => {
  const { html } = sdk.ui
  return (props) => html`<${sdk.defaults.GamepadView} ...${props} skin="shelf-pad" />`
}
