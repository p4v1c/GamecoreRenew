/**
 * Orbit's handovers — the seconds between the interface and the game.
 *
 * Orbit had none. It declared `launch.ms: 500` in its manifest, so the host
 * dutifully held the launch for half a second and Orbit drew nothing in it:
 * the player pressed ✕, the screen sat still, and then the emulator appeared.
 * A pause with nothing in it does not read as ceremony, it reads as lag.
 *
 * Three moments, one shape. The reference is the PS5's: the console does not
 * cut to a game, it *travels* to one. A soft field of light gathers at the
 * centre, the interface falls back and away from the viewer, and the light
 * takes the screen. Coming back reverses it exactly — the light parts and the
 * interface returns from behind it — and suspending is the same reversal
 * played shorter, because the player did not ask to go anywhere.
 *
 *   launch   the interface recedes, the light closes over it
 *   resume   the same, for a game that was already frozen
 *   suspend  the light parts and the interface comes forward again
 *
 * The host decides when: `transition` in the store is set by the launch hold,
 * by the session bar's resume, and by the backgrounded event. This file is only
 * ever asked what it looks like — which is the half a theme should own.
 *
 * ## Timing
 *
 * `TRAVEL_MS` below is the whole of the launch and resume animation, and it
 * MUST be what `theme.json` declares as `launch.ms`. The host holds the call
 * for exactly that long, so a smaller number here means the light is still
 * moving when the emulator takes the screen, and a larger one means the player
 * waits on a finished picture. `backend/tests/test_theme_ceremony.py` asserts
 * the two agree, because nothing else can.
 */

/** Motion plus a settled field of light. Must equal `launch.ms` in theme.json. */
export const TRAVEL_MOTION_MS = 930
export const TRAVEL_SETTLE_MS = 220
export const TRAVEL_MS = 1150

/** The return. Not held by anything — the game is frozen before this starts. */
export const RETURN_MS = 900

/** Lets React paint the last animation frame before removing the overlay. */
const HIDE_GRACE_MS = 120

export function createCeremony(sdk) {
  const {html, useState, useEffect} = sdk.ui

  return function Ceremony() {
    const transition = sdk.nav.use((s) => s.transition)
    // Kept one beat past the store clearing it, so the picture can finish
    // rather than being unmounted mid-frame. The host clears `transition` the
    // moment the emulator owns the screen, which is the right moment for the
    // host and one frame too early for an animation.
    const [shown, setShown] = useState(null)

    useEffect(() => {
      if (transition) { setShown(transition); return }
      if (!shown) return
      const hold = setTimeout(() => setShown(null), HIDE_GRACE_MS)
      return () => clearTimeout(hold)
    }, [transition, shown])

    if (!shown) return null

    const going = shown === 'launch' || shown === 'resume'
    return html`<div className="orbit-ceremony" data-move=${shown}
                     data-dir=${going ? 'away' : 'back'} aria-hidden="true">
      <div className="orbit-ceremony-field" />
      <div className="orbit-ceremony-core" />
      <div className="orbit-ceremony-ring" />
    </div>`
  }
}
