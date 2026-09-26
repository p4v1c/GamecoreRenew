/**
 * Orbit's handovers between the interface and the game (PS5-style travel):
 *
 *   launch   the interface recedes, the light closes over it
 *   resume   the same, for a frozen game
 *   suspend  the light parts and the interface comes forward
 *
 * The host decides WHEN (`transition` in the store); this file only draws it.
 * TRAVEL_MS MUST equal `launch.ms` in theme.json: the host holds the launch
 * that long. backend/tests/test_theme_ceremony.py enforces it.
 */

/** Motion plus a settled field of light. Must equal `launch.ms` in theme.json. */
export const TRAVEL_MOTION_MS = 300
export const TRAVEL_SETTLE_MS = 100
export const TRAVEL_MS = 400

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
