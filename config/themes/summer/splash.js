/**
 * The boot animation: sunrise over the horizon, at the hour it actually is.
 *
 * Mandatory — a theme dresses the whole UI or it does not load, and a beach
 * dashboard behind the stock purple splash is exactly the half-and-half look
 * the rule exists to prevent.
 *
 * Kept to CSS transforms and opacity on five elements: this runs during boot,
 * while the backend is still starting and the ocean has not compiled its
 * shaders yet, so it must cost nothing. onDone is the host's — we call it once,
 * and the host cuts us off anyway if we ever failed to.
 */
import { todColors } from './ocean.js'

/**
 * The whole timeline lives here, and the stylesheet reads it back through the
 * custom properties set on the root below — so the JS timers and the CSS
 * transitions cannot drift apart when these are tuned.
 */
const RISE_MS = 1700   // sun clears the horizon — kept short, the opening drags
const HOLD_MS = 2500   // beat on the finished frame, where the time is better spent
const FADE_MS = 1800   // hand over to the shell
const WORD_DELAY_MS = 150    // the wordmark is up almost immediately
const WORD_MS = 950

export const createSplash = (sdk) => {
  const { html, useState, useEffect } = sdk.ui
  return ({ onDone }) => {
    const [c] = useState(() => todColors())
    const [phase, setPhase] = useState('rise')   // rise → hold → out

    useEffect(() => {
      const timers = [
        setTimeout(() => setPhase('hold'), RISE_MS),
        setTimeout(() => setPhase('out'), RISE_MS + HOLD_MS),
        setTimeout(onDone, RISE_MS + HOLD_MS + FADE_MS),
      ]
      return () => timers.forEach(clearTimeout)
    }, [onDone])

    const risen = phase !== 'rise'
    return html`
      <div class="sm-splash" data-out=${phase === 'out' ? '1' : '0'}
           style=${{
             background: `linear-gradient(180deg, ${c.skyTop} 0%, ${c.skyMid} 42%, ${c.skyLow} 68%, ${c.sandNear} 100%)`,
             '--sm-rise': `${RISE_MS}ms`,
             '--sm-fade': `${FADE_MS}ms`,
             '--sm-word': `${WORD_MS}ms`,
             '--sm-word-delay': `${WORD_DELAY_MS}ms`,
           }}>
        <div class="sm-splash-sun" data-up=${risen ? '1' : '0'}
             style=${{ background: c.disc, boxShadow: `0 0 90px 30px ${c.glow}` }} />
        <div class="sm-splash-sea" style=${{ background: `linear-gradient(180deg, ${c.seaDeep}, ${c.seaShallow})` }} />
        <div class="sm-splash-word" data-up=${risen ? '1' : '0'}>
          <span class="sm-diamond" /> GAMECORE
        </div>
      </div>`
  }
}
