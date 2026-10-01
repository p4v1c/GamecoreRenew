import {mark} from '../lib/drawings.js'

const INTRO_MS = 2600
const FADE_MS = 520
const WORD = 'GAMECORE'
// Confetti: angle (deg), distance (vmin), colour, delay (ms).
const BITS = [
  [-80, 30, '#f950a3', 0], [-40, 34, '#ffe66b', 40], [0, 31, '#5931a0', 80], [40, 35, '#f950a3', 20],
  [80, 30, '#ffe66b', 60], [130, 28, '#5931a0', 30], [180, 33, '#fffdf7', 90], [230, 29, '#f950a3', 50],
]

/** The boot: the letters drop in one by one like jelly, the mark lands with a
 * squash, a single burst of confetti, then the last frame is held until the
 * host says the interface is ready (SDK 4 `bootReady`). */
export function createSplash(sdk) {
  const {html, useState, useEffect, useRef} = sdk.ui
  return function Splash({onDone, bootReady}) {
    const [held, setHeld] = useState(false)
    const [leaving, setLeaving] = useState(false)
    const timer = useRef(null)
    const done = useRef(onDone)
    done.current = onDone

    useEffect(() => {
      const reduced = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      const t = setTimeout(() => setHeld(true), reduced ? 150 : INTRO_MS)
      return () => { clearTimeout(t); clearTimeout(timer.current) }
    }, [])
    useEffect(() => {
      // An older host passes no `bootReady` at all: only `false` means wait.
      if (!held || bootReady === false || timer.current !== null) return
      setLeaving(true)
      timer.current = setTimeout(() => done.current(), FADE_MS)
    }, [held, bootReady])

    return html`<div className="jl-splash" data-out=${leaving ? 'true' : 'false'}
                     style=${{'--jl-fade': `${FADE_MS}ms`}} role="status" aria-label="GameCore is starting">
      <div className="jl-splash-floor" aria-hidden="true" />
      <div className="jl-splash-stage">
        <span className="jl-splash-mark" aria-hidden="true" dangerouslySetInnerHTML=${{__html: mark()}} />
        <div className="jl-splash-word" aria-hidden="true">
          ${[...WORD].map((c, i) => html`<span key=${i} style=${{'--i': i}}>${c}</span>`)}
        </div>
        <span className="jl-splash-edition">Jelly edition</span>
        <span className="jl-splash-burst" aria-hidden="true">
          ${BITS.map(([a, d, c, delay], i) => html`<i key=${i} style=${{'--a': `${a}deg`, '--d': `${d}vmin`,
            '--c': c, '--delay': `${delay}ms`}} />`)}
        </span>
      </div>
    </div>`
  }
}
