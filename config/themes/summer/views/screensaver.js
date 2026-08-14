/**
 * Standby: the library's boxes, turning slowly in the dark.
 *
 * The same `Box3D` the detail panel uses, so a game looks the same asleep as
 * awake — and the idle drift that exists there to hint "this turns" is exactly
 * what a screensaver wants anyway. Nobody is holding the stick at this point,
 * so the box simply turns on its own.
 *
 * The behaviour is the host's and is reproduced exactly, because getting it
 * wrong strands the box:
 *
 *   standby:screensaver → the slideshow
 *   standby:sleep       → plain black. The backend cuts the screen through
 *                         DPMS; black avoids a bright flash either side of it,
 *                         and everything here unmounts so nothing animates
 *                         against a dark panel.
 *   standby:exit        → gone
 *
 * and local pointer/keyboard input wakes the box, since a mouse is not a
 * controller — a pad's first press is swallowed into a wake by the host's input
 * bus, which is also why the stage below is READ from the store rather than
 * rebuilt from the three events: the bus lets go of the pad after a grace
 * period if the box never answers, and an overlay built from its own copy would
 * still be on screen at that point. A black rectangle over a live cursor is the
 * fault the guard exists to prevent.
 *
 * One media catalogue is fetched per game *as it comes up*, not for the whole
 * library at once: a shelf of two hundred games would otherwise fire two
 * hundred requests the moment the box goes idle, which is the opposite of what
 * standby is for.
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
