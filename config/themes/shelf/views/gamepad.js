/**
 * The controller screen, as an instruction-manual page pinned to the wall.
 *
 * The host's markup (`sdk.defaults.GamepadView`) dressed by css/controller.css;
 * `callouts` letters the diagram and adds the manual's key. Every prop passes
 * through, so the diagram, the wizard and the hold gesture stay the host's.
 * Props: frontend/src/components/modals/gamepad/types.ts
 */
export const createGamepadView = (sdk) => {
  const { html } = sdk.ui
  return (props) => html`<${sdk.defaults.GamepadView} ...${props} skin="shelf-pad" callouts=${true} />`
}
