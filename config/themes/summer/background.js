/** The ocean, as the page background. The renderer itself lives in ocean.js. */
import { createOcean } from './ocean.js'

export const createBackground = (sdk, useIdle) => {
  const { html, useEffect, useRef } = sdk.ui
  return () => {
    const ref = useRef(null)
    const oceanRef = useRef(null)
    const idle = useIdle()

    useEffect(() => {
      if (!ref.current) return
      oceanRef.current = createOcean(ref.current)
      return () => oceanRef.current?.stop()
    }, [])

    useEffect(() => { oceanRef.current?.setPaused(idle) }, [idle])

    // No z-index here on purpose: the shell puts this behind everything.
    return html`<canvas ref=${ref} class="sm-ocean" aria-hidden="true" />`
  }
}
