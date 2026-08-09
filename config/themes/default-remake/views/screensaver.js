/**
 * Standby: the cover slideshow, and the black screen behind sleep.
 *
 * Driven entirely by backend WebSocket events, which a theme receives in full
 * through `sdk.system.onWsEvent` — no SDK change was needed here either.
 *
 * `sleep` draws black rather than nothing on purpose: the backend turns the
 * panel off through DPMS, and anything bright on screen either side of that is
 * a flash in a dark room.
 */
export const createScreensaver = (sdk) => {
  const { html, useState, useEffect, useRef, motion, AnimatePresence } = sdk.ui

  const ROTATE_MS = 9000

  return () => {
    const [stage, setStage] = useState('off')
    const [covers, setCovers] = useState([])
    const [idx, setIdx] = useState(0)
    const [clock, setClock] = useState('')
    const loaded = useRef(false)

    useEffect(() => {
      const offs = [
        sdk.system.onWsEvent('standby:screensaver', () => setStage('screensaver')),
        sdk.system.onWsEvent('standby:sleep', () => setStage('sleep')),
        sdk.system.onWsEvent('standby:exit', () => setStage('off')),
      ]
      return () => offs.forEach(o => o())
    }, [])

    // Pads are woken backend-side through evdev; this covers a mouse or a
    // keyboard, which is how anyone working on the box remotely wakes it.
    useEffect(() => {
      if (stage === 'off') return
      const wake = () => { sdk.api.standby.exit().catch(() => {}) }
      window.addEventListener('pointermove', wake)
      window.addEventListener('keydown', wake)
      return () => {
        window.removeEventListener('pointermove', wake)
        window.removeEventListener('keydown', wake)
      }
    }, [stage])

    useEffect(() => {
      if (stage !== 'screensaver') return
      const tick = () => setClock(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
      tick()
      const t = setInterval(tick, 20000)
      return () => clearInterval(t)
    }, [stage])

    useEffect(() => {
      if (stage !== 'screensaver' || loaded.current) return
      loaded.current = true
      let cancelled = false
      ;(async () => {
        try {
          const systems = await sdk.api.systems.list()
          const emus = systems.filter(s => s.kind === 'emulator')
          const lists = await Promise.all(
            emus.map(s => sdk.api.games.list(s.id).then(g => ({ s, g })).catch(() => null)),
          )
          if (cancelled) return
          const out = []
          for (const entry of lists.filter(Boolean)) {
            for (const g of entry.g.slice(0, 12)) {
              out.push({
                url: sdk.api.media.url(entry.s.id, g.filename, 'box-front'),
                name: sdk.format.gameName(g.display_name),
              })
            }
          }
          // Deterministic order rather than shuffled: a slideshow that reorders
          // itself on every wake looks like it lost its place.
          setCovers(out)
        } catch { /* an empty slideshow is still a valid screensaver */ }
      })()
      return () => { cancelled = true }
    }, [stage])

    useEffect(() => {
      if (stage !== 'screensaver' || covers.length < 2) return
      const t = setInterval(() => setIdx(i => (i + 1) % covers.length), ROTATE_MS)
      return () => clearInterval(t)
    }, [stage, covers.length])

    if (stage === 'off') return null
    if (stage === 'sleep') return html`<div class="dr-sleep" />`

    const cover = covers[idx]
    return html`
      <div class="dr-saver">
        <${AnimatePresence} mode="wait">
          ${cover ? html`
            <${motion.div} key=${cover.url}
              initial=${{ opacity: 0, scale: 1.04 }}
              animate=${{ opacity: 1, scale: 1 }}
              exit=${{ opacity: 0, scale: 0.98 }}
              transition=${{ duration: 1.1 }}
              class="dr-saver-art">
              <img src=${cover.url} alt="" onError=${(e) => { e.target.style.visibility = 'hidden' }} />
              <span>${cover.name}</span>
            <//>` : null}
        <//>
        <div class="dr-saver-clock">${clock}</div>
      </div>`
  }
}
