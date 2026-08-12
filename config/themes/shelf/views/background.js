/**
 * The wall.
 *
 * Two flat elements: the paper, and the pattern over it. No canvas, no picture
 * — the pattern is `--gc-paper-pattern`, defined once in theme.css and painted
 * identically by the settings screen. That single definition is the point: the
 * wall and Settings each used to draw their own motif, a Truchet weave here and
 * the reference capture's rings-and-arcs there, and they are meant to be the
 * same wall seen from two screens.
 *
 * It no longer takes the colour of the box you are facing. It did, which is why
 * the pattern used to be a *mask* over a solid colour — `background-color`
 * transitions and an image does not. The retint is retired on the owner's call,
 * so the mask had nothing left to do.
 *
 * The drift is one `translate3d` on one element, and it stops dead while a game
 * runs or the box sleeps. No z-index anywhere: the shell already placed this
 * behind everything.
 */
export const createBackground = (sdk, accent, useIdle) => {
  const { html } = sdk.ui

  return () => {
    const idle = useIdle()

    return html`
      <div class="cz-wall" data-idle=${idle ? '1' : '0'} aria-hidden="true">
        <div class="cz-wall-pattern" />
        <div class="cz-wall-vignette" />
      </div>`
  }
}
