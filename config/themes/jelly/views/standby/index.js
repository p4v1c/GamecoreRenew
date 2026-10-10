import {systemName} from '../../lib/catalog.js'
import {createCaption} from './caption.js'
import {createEngine} from './engine.js'

/** The collection's games in the shape the standby deals. */
const libraryGames = (games) => games.map((g) => ({
  key: g.key, systemId: g.systemId, filename: g.gameKey, title: g.title,
  systemName: systemName(g.system), lastPlayed: g.lastPlayed,
}))

/** A box as a root-relative rect, or null before it is laid out. */
function rectIn(root, el) {
  if (!el) return null
  const o = root.getBoundingClientRect()
  const r = el.getBoundingClientRect()
  if (!r.width || !r.height) return null
  return {left: r.left - o.left, top: r.top - o.top, right: r.right - o.left, bottom: r.bottom - o.top}
}

/**
 * Jelly's standby, the Shell's `screensaver`: the cyan floor, jellies holding
 * the library's covers, one now and then grown in the centre, the caption and
 * clock. No clips: the owner wanted Jelly's standby to be the covers alone, so
 * it never asks for the standby playlist and no video is ever decoded here.
 * Driven by the store's `standby` stage like the host's: `sleep` mounts a
 * black screen and nothing else (DPMS has the screen off), and leaving
 * `screensaver` unmounts the room, which stops the loop and empties the video.
 *
 * Undefined on a host older than SDK 12 (no `useLocalWake`, no `playedAgo`):
 * the Shell then keeps its own slideshow.
 */
export function createStandby(sdk, {collection}) {
  if (!sdk.defaults?.useLocalWake || !sdk.format?.playedAgo) return undefined
  const {html, useEffect, useRef, useState} = sdk.ui
  const {Caption, Clock} = createCaption(sdk)

  function Room() {
    const root = useRef(null)
    const layer = useRef(null)
    const captionBox = useRef(null)
    const clockBox = useRef(null)
    const engine = useRef(null)
    const [game, setGame] = useState(null)
    // The jellies are the library's covers and nothing else, so a box that
    // boots straight into standby, before Home has loaded the collection,
    // asks for the consoles itself; otherwise the floor would stay empty.
    const [systems, setSystems] = useState(null)
    useEffect(() => {
      if (collection.get().games.length) return
      sdk.api.systems.list().then(setSystems).catch(() => {})
    }, [])
    const library = collection.useCollection(systems)

    const zones = () => [rectIn(root.current, captionBox.current), rectIn(root.current, clockBox.current)]
      .filter(Boolean)

    useEffect(() => {
      const reduced = !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      engine.current = createEngine({root: root.current, layer: layer.current,
        games: libraryGames(collection.get().games || []), reel: [], reduced, onCaption: setGame})
      engine.current.setZones(zones())
      engine.current.start()
      const resize = () => engine.current?.measure()
      window.addEventListener('resize', resize)
      return () => {
        window.removeEventListener('resize', resize)
        engine.current?.stop()
        engine.current = null
      }
    }, [])

    // Standby can start before the collection has loaded (a boot straight
    // into standby): its games join the deck when they arrive.
    useEffect(() => { engine.current?.addGames(libraryGames(library.games || [])) }, [library.games])

    // A new title changes the caption's width: the zone follows it.
    useEffect(() => { engine.current?.setZones(zones()) }, [game])

    return html`<div ref=${root} className="jl-standby" aria-label="Standby">
      <div className="jl-sb-dots" aria-hidden="true" />
      <div ref=${layer} className="jl-sb-layer" aria-hidden="true" />
      <${Caption} game=${game} boxRef=${captionBox} />
      <${Clock} boxRef=${clockBox} />
    </div>`
  }

  return function JellyStandby() {
    const stage = sdk.nav.use((s) => s.standby)
    sdk.defaults.useLocalWake(stage)
    if (stage === 'off') return null
    if (stage === 'sleep') return html`<div className="jl-standby-sleep" />`
    return html`<${Room} />`
  }
}
