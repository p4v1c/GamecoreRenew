/**
 * Standby: the library's boxes turning slowly in the dark (the same Box3D).
 *
 *   standby:screensaver → slideshow
 *   standby:sleep       → plain black, everything unmounted (DPMS is off)
 *   standby:exit        → gone
 *
 * The stage is READ from the store, not rebuilt from events: the input bus
 * releases the pad after a grace period, and a private copy would leave a
 * black overlay over a live cursor. Pointer/keyboard input wakes the box.
 * Media is fetched per game as it comes up, never for the whole library.
 */

const ROTATE_MS = 9000

export const createScreensaver = (sdk, Box3D) => {
  const { html, useState, useEffect } = sdk.ui

  /** Every game on the box, flattened, in one pass. */
  const useShelf = (active) => {
    const [shelf, setShelf] = useState([])
    useEffect(() => {
      if (!active || shelf.length) return
      let cancelled = false
      ;(async () => {
        try {
          const systems = await sdk.api.systems.list()
          const emus = systems.filter(s => s.kind === 'emulator')
          const lists = await Promise.all(emus.map(s =>
            sdk.api.games.list(s.id)
              .then(g => g.map(x => ({ systemId: s.id, filename: x.filename, name: x.display_name })))
              .catch(() => [])))
          const all = lists.flat()
          // Shuffled, so an evening of standby is not the same five games in
          // the same order every time.
          for (let i = all.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1))
            ;[all[i], all[j]] = [all[j], all[i]]
          }
          if (!cancelled) setShelf(all)
        } catch { /* an empty shelf just means the clock, which is fine */ }
      })()
      return () => { cancelled = true }
    }, [active, shelf.length])
    return shelf
  }

  /** The media catalogue of one game, fetched only when it is on screen. */
  const useMediaOf = (game) => {
    const [media, setMedia] = useState(null)
    useEffect(() => {
      setMedia(null)
      if (!game || !sdk.api.media) return
      let cancelled = false
      sdk.api.media.list(game.systemId, game.filename)
        .then(idx => { if (!cancelled && idx?.found) setMedia(idx.media || null) })
        .catch(() => {})
      return () => { cancelled = true }
    }, [game?.systemId, game?.filename])
    return media
  }

  // Last resort when nothing is scraped: the flat cover, which is what the
  // host's own screensaver shows. Box3D wants a component of this shape.
  const PlainCover = ({ filename, systemId }) => html`
    <img class="sm-saver-flat"
         src=${`/api/covers/${systemId}/${encodeURIComponent(filename)}`} alt=""
         onError=${(e) => { e.target.style.visibility = 'hidden' }} />`

  return () => {
    const stage = sdk.nav.use(s => s.standby)
    const [idx, setIdx] = useState(0)
    const [clock, setClock] = useState('')

    // A mouse is not a controller: the backend never sees it.
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

    const shelf = useShelf(stage === 'screensaver')
    const game = shelf.length ? shelf[idx % shelf.length] : null
    const media = useMediaOf(stage === 'screensaver' ? game : null)

    useEffect(() => {
      if (stage !== 'screensaver') return
      const tick = () => setClock(new Date().toLocaleTimeString('fr-FR',
        { hour: '2-digit', minute: '2-digit' }))
      tick()
      const c = setInterval(tick, 10000)
      const r = setInterval(() => setIdx(i => i + 1), ROTATE_MS)
      return () => { clearInterval(c); clearInterval(r) }
    }, [stage])

    if (stage === 'off') return null
    // Asleep: nothing at all. Not a paused slideshow, not a dimmed one —
    // the screen is about to be switched off and anything still drawing is
    // work done for a dark panel.
    if (stage === 'sleep') return html`<div class="sm-saver" data-sleep="1" />`

    return html`
      <div class="sm-saver">
        ${game ? html`
          <div class="sm-saver-stage" key=${idx}>
            <${Box3D} systemId=${game.systemId} filename=${game.filename}
                      media=${media} color="#F0761E" Cover=${PlainCover}
                      height=${560} />
            <div class="sm-saver-name">${game.name}</div>
          </div>` : null}
        <div class="sm-saver-clock">${clock}</div>
        <div class="sm-saver-hint">PRESS ANY BUTTON TO WAKE</div>
      </div>`
  }
}
