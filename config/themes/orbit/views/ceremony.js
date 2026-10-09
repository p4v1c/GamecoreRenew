/**
 * Orbit's handovers between the interface and the game:
 *
 *   launch   the interface falls back into the night and the stars streak
 *            past, as if the box jumped to the game; it lands on night blue
 *   resume   the same, for a frozen game
 *   suspend  the night opens on a thin ring of light and the interface
 *            comes forward through it
 *
 * It used to end on a swelling white core that filled the screen: on a TV in a
 * dark room that read as a flash, and the game then appeared out of white. The
 * jump ends dark instead, which is also the colour an emulator starts on.
 *
 * The host decides WHEN (`transition` in the store); this file only draws it.
 * TRAVEL_MS MUST equal `launch.ms` in theme.json: the host holds the launch
 * that long. backend/tests/test_theme_ceremony.py enforces it, and keeps the
 * hold at 400 ms or less: Orbit launches in place and does not make the player
 * wait on an animation.
 */

/** Motion plus a settled field of night. Must equal `launch.ms` in theme.json. */
export const TRAVEL_MOTION_MS = 300
export const TRAVEL_SETTLE_MS = 100
export const TRAVEL_MS = 400

/** The return. Not held by anything — the game is frozen before this starts. */
export const RETURN_MS = 900

/** Lets React paint the last animation frame before removing the overlay. */
const HIDE_GRACE_MS = 120

/** The star streaks: angle, start delay and length, fixed so every jump is the
 *  same picture. A small LCG rather than Math.random, for exactly that. */
const STREAKS = (() => {
  let seed = 7
  const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 }
  return Array.from({length: 44}, (_, i) => ({
    angle: (i / 44) * 360 + rnd() * 6,
    delay: Math.round(rnd() * 90),
    length: 10 + Math.round(rnd() * 16),
    reach: 46 + Math.round(rnd() * 22),
  }))
})()

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
      <div className="orbit-ceremony-stars">
        ${going ? STREAKS.map((s, i) => html`<i key=${i} style=${{
          '--a': `${s.angle}deg`, '--d': `${s.delay}ms`,
          '--l': `${s.length}vmin`, '--r': `${s.reach}vmax`,
        }} />`) : null}
      </div>
      <div className="orbit-ceremony-ring" />
    </div>`
  }
}
