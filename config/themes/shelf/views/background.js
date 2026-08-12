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
 * It does not move. It used to drift a tile every 140 s, and that is what put
 * it out of step with the settings screen: that screen paints the same pattern
 * on its own element, mounted when it opens, so it started its own timeline and
 * the wallpaper visibly shifted as you went in. Two independently animated
 * surfaces are in phase only by accident, and no amount of tuning fixes that —
 * so the movement went and the pattern is continuous across the whole box.
 *
 * `useIdle` is still taken and still ignored here: it is the shell's, other
 * surfaces read it, and the signature is what index.js passes.
 *
 * No z-index anywhere: the shell already placed this behind everything.
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
