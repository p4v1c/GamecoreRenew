/**
 * The ocean, as the page background — and the sound of it.
 *
 * The renderer lives in ocean.js, the surf in ambience.js. They are driven from
 * here because they answer the same two questions: what time is it, and is
 * anyone watching? Both stop while a game runs or the box sleeps.
 */
import { createOcean } from '../lib/ocean.js'
import { currentTod } from '../lib/ocean.js'
import { createAmbience } from '../lib/ambience.js'

export const createBackground = (sdk, useIdle) => {
  const { html, useEffect, useRef } = sdk.ui
  return () => {
    const ref = useRef(null)
    const oceanRef = useRef(null)
    const soundRef = useRef(null)
    const idle = useIdle()

    useEffect(() => {
      if (!ref.current) return
      oceanRef.current = createOcean(ref.current)
      return () => oceanRef.current?.stop()
    }, [])

    // The ambience is optional in a way the picture is not: no AudioContext
    // (or a browser that refuses one before a gesture) simply means silence.
    useEffect(() => {
      const ctx = sdk.system.getAudioContext?.()
      if (!ctx) return
      let amb
      try { amb = createAmbience(ctx) } catch { return }
      soundRef.current = amb
      amb.setTod(currentTod().tod)
      const t = setInterval(() => amb.setTod(currentTod().tod), 60000)
      return () => { clearInterval(t); soundRef.current = null; amb.stop() }
    }, [])

    // The player's sound setting wins, always — and it can change while we run.
    useEffect(() => {
      const apply = () => {
        const s = sdk.system.sound
        soundRef.current?.setLevel(idle || !s?.enabled ? 0 : (s?.volume ?? 0.6))
      }
      apply()
      const t = setInterval(apply, 2000)
      return () => clearInterval(t)
    }, [idle])

    useEffect(() => { oceanRef.current?.setPaused(idle) }, [idle])

    // No z-index here on purpose: the shell puts this behind everything.
    return html`<canvas ref=${ref} class="sm-ocean" aria-hidden="true" />`
  }
}
