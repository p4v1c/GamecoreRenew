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
 */
const DROP_MS = 1150
const WORD_DELAY_MS = 680
const HOLD_MS = 900
const FADE_MS = 620

export const createSplash = (sdk) => {
  const { html, useState, useEffect } = sdk.ui

  return ({ onDone }) => {
    const [out, setOut] = useState(false)

    useEffect(() => {
      const timers = [
        setTimeout(() => setOut(true), DROP_MS + HOLD_MS),
        setTimeout(onDone, DROP_MS + HOLD_MS + FADE_MS),
      ]
      return () => timers.forEach(clearTimeout)
    }, [onDone])

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
