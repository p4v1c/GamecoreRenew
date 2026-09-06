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
 *
 * `bootReady` is the SDK 4 half of that contract. The sunrise is a duration;
 * the box being usable is not. So the hold beat lasts at least as long as it
 * was written to, and longer if the interface behind is not ready yet — the
 * sun simply stays up. `!== false` because an older host passes nothing, and
 * waiting for a prop that never arrives is a box that never boots.
 */
import { todColors } from '../lib/ocean.js'

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
  const { html, useState, useEffect, useRef } = sdk.ui
  return ({ onDone, bootReady }) => {
    const [c] = useState(() => todColors())
    const [phase, setPhase] = useState('rise')   // rise → rise-done → held → out
    const allowed = bootReady !== false

    useEffect(() => {
      const timers = [
        setTimeout(() => setPhase('rise-done'), RISE_MS),
        setTimeout(() => setPhase('held'), RISE_MS + HOLD_MS),
      ]
      return () => timers.forEach(clearTimeout)
    }, [])

    // The exit is armed once and cleared only on the way out.
    //
    // Not by this effect's own cleanup, which is the mistake worth recording:
    // setting the phase re-runs the effect, the cleanup cancels the timer it
    // has just armed, and the guard at the top then refuses to arm another —
    // an animation that reaches its last frame and stays there for good. The
    // ref is what makes "already leaving" a fact rather than a phase.
    const leaving = useRef(0)
    useEffect(() => () => clearTimeout(leaving.current), [])
    useEffect(() => {
      if (leaving.current || phase !== 'held' || !allowed) return
      setPhase('out')
      leaving.current = setTimeout(onDone, FADE_MS)
    }, [phase, allowed, onDone])

    const risen = phase !== 'rise'   // every phase after the sun is up
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
