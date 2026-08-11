/**
 * The wall.
 *
 * Three flat layers and no canvas: a paper base, a soft worm and an outlined
 * one, each a solid colour behind an SVG mask. That is what makes the retint
 * possible at all — `background-color` transitions, a picture does not, and the
 * whole point of this theme is that the room takes the colour of the box you
 * are holding.
 *
 * The drift is one `translate3d` on one element, and it stops dead while a game
 * runs or the box sleeps. No z-index anywhere: the shell already placed this
 * behind everything.
 */
import { WALL_SOFT, WALL_LINE, WALL_TILE } from '../lib/paper.js'
import { vars } from '../lib/accent.js'

export const createBackground = (sdk, accent, useIdle) => {
  const { html } = sdk.ui

  return () => {
    const a = accent.use()
    const idle = useIdle()

    return html`
      <div class="cz-wall" data-idle=${idle ? '1' : '0'} style=${{
        ...vars(a),
        '--wall-soft': WALL_SOFT,
        '--wall-line': WALL_LINE,
        '--wall-tile': `${WALL_TILE}px`,
      }} aria-hidden="true">
        <div class="cz-wall-soft" />
        <div class="cz-wall-line" />
        <div class="cz-wall-vignette" />
      </div>`
  }
}
