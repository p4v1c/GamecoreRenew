/**
 * The controller screen, in sea glass over the ocean.
 *
 * The host's markup (`sdk.defaults.GamepadView`) dressed by css/controller.css:
 * every prop passes through, so the diagram, the wizard and the hold gesture
 * stay the host's. Props: frontend/src/components/modals/gamepad/types.ts
 */
export const createGamepadView = (sdk) => {
  const { html } = sdk.ui
  return (props) => html`<${sdk.defaults.GamepadView} ...${props} skin="summer-pad" />`
}
