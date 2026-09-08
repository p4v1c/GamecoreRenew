export function createSplash(sdk) {
  const {html, useState, useEffect, useRef} = sdk.ui
  return function Splash({onDone, bootReady}) {
    const [held, setHeld] = useState(false)
    const [leaving, setLeaving] = useState(false)
    const timer = useRef(null)
    const done = useRef(onDone)
    done.current = onDone
    useEffect(() => {
      const enter = setTimeout(() => setHeld(true), 1100)
      return () => {clearTimeout(enter); clearTimeout(timer.current)}
    }, [])
    useEffect(() => {
      if (!held || bootReady === false || timer.current !== null) return
      setLeaving(true)
      timer.current = setTimeout(() => done.current(), 420)
    }, [held, bootReady])
    return html`<div className="orbit-splash" data-out=${leaving ? 'true' : 'false'}><span className="orbit-orb" />
      <div className="orbit-splash-word">GAMECORE<small>O R B I T</small></div><p>Your next escape.</p></div>`
  }
}
