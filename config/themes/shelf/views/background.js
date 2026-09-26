/**
 * The wall: paper plus `--gc-paper-pattern`, the same definition Settings
 * paints, so both screens show one continuous wall. It does not move (two
 * independently animated surfaces are in phase only by accident) and does not
 * retint. `useIdle` is accepted and ignored to keep index.js's signature.
 * No z-index: the shell already placed it behind everything.
 */
export const createBackground = (sdk, accent, useIdle) => {
  const { html } = sdk.ui

  return () => {
    return html`
      <div class="cz-wall" aria-hidden="true">
        <div class="cz-wall-pattern" />
        <div class="cz-wall-vignette" />
      </div>`
  }
}
