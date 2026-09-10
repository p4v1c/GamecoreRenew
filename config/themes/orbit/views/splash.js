const INTRO_MS = 4800
const FADE_MS = 700

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
      const enter = setTimeout(() => setHeld(true), reduced ? 100 : INTRO_MS)
      return () => {clearTimeout(enter); clearTimeout(timer.current); timer.current = null}
    }, [])
    useEffect(() => {
      if (!held || bootReady === false || timer.current !== null) return
      setLeaving(true)
      timer.current = setTimeout(() => done.current(), FADE_MS)
    }, [held, bootReady])
    return html`<div className="orbit-splash" data-out=${leaving ? 'true' : 'false'}
      style=${{'--orbit-boot-fade': `${FADE_MS}ms`}} role="status" aria-label="Starting GameCore Orbit">
      <div className="orbit-boot-glow" aria-hidden="true" />
      <div className="orbit-boot-ring orbit-boot-ring-a" aria-hidden="true" />
      <div className="orbit-boot-ring orbit-boot-ring-b" aria-hidden="true" />
      <div className="orbit-boot-identity">
        <svg className="orbit-boot-mark" viewBox="0 0 36 36" aria-hidden="true">
          <path d="M19 3 5 11v15l13 8 13-8V15H18v7h6v1l-6 4-6-4V15l10-6z" fill="currentColor" />
        </svg>
        <div className="orbit-splash-word">GAMECORE<small>ORBIT</small></div>
        <span className="orbit-boot-line" aria-hidden="true" />
        <p>Your next escape.</p>
      </div>
    </div>`
  }
}
