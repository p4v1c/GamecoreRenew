/**
 * Boot: a cartridge going into a slot.
 *
 * Mandatory, and cheap by necessity — this plays while the backend is still
 * coming up, so it is four elements, two properties and no image. The drop
 * overshoots and settles rather than easing to a stop, because that is the one
 * thing a cartridge does that nothing else does.
 *
 * The timings live here and are handed to the stylesheet as custom properties,
 * so the JS clock and the CSS clock cannot drift apart when either is tuned.
 * `onDone` is the host's: we call it once, and it stops waiting after 20s
 * whether we do or not.
 *
 * `bootReady` is the other half of that contract, and it is why this theme
 * declares SDK 4. The cartridge going in is a duration; the box being usable
 * is not, and the two used to be the same event. So the animation now ends on
 * a HELD frame — the cartridge seated, the wordmark up — and leaves only when
 * the host says the interface behind it is worth showing. Nothing is added to
 * a boot that was already finished: on a fast box the hold is one frame.
 *
 * `bootReady !== false` rather than `bootReady`: an older host passes nothing
 * at all, and a splash that waited for a prop that will never arrive is a box
 * that never boots.
 */
const DROP_MS = 1150
const WORD_DELAY_MS = 680
const HOLD_MS = 900
const FADE_MS = 620

export const createSplash = (sdk) => {
  const { html, useState, useEffect, useRef } = sdk.ui

  return ({ onDone, bootReady }) => {
    const [out, setOut] = useState(false)
    const [seated, setSeated] = useState(false)   // the cartridge is in; the frame holds
    const allowed = bootReady !== false

    useEffect(() => {
      const t = setTimeout(() => setSeated(true), DROP_MS + HOLD_MS)
      return () => clearTimeout(t)
    }, [])

    // Armed once, cleared only on unmount. Writing it as this effect's own
    // cleanup works here by luck — `out` is not in the dependency list, so the
    // effect does not re-run — and the same shape in Summer cancelled the
    // timer it had just armed. One mechanism in both, and neither depends on
    // which state happens to be a dependency.
    const leaving = useRef(0)
    useEffect(() => () => clearTimeout(leaving.current), [])
    useEffect(() => {
      if (leaving.current || !seated || !allowed) return
      setOut(true)
      leaving.current = setTimeout(onDone, FADE_MS)
    }, [seated, allowed, onDone])

    return html`
      <div class="cz-splash" data-out=${out ? '1' : '0'} style=${{
        '--drop': `${DROP_MS}ms`,
        '--word-delay': `${WORD_DELAY_MS}ms`,
        '--fade': `${FADE_MS}ms`,
      }}>
        <div class="cz-splash-slot">
          <div class="cz-splash-cart">
            <div class="cz-cart">
              <div class="cz-cart-shoulder" />
              <div class="cz-cart-label">
                <div class="cz-cart-art" style=${{
                  background: 'linear-gradient(120deg, #1C1B19, #35322C 60%, #1C1B19)',
                }} />
              </div>
              <div class="cz-cart-grip" />
              <i class="cz-cart-screw cz-cart-screw-l" />
              <i class="cz-cart-screw cz-cart-screw-r" />
            </div>
          </div>
        </div>

        <div class="cz-splash-word"><span class="cz-splash-mark" /> GAMECORE</div>
      </div>`
  }
}
