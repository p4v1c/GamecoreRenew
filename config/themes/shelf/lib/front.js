/**
 * Which picture is a game's box front, and what shape the box is.
 *
 * The host's cover route is the first choice (the rest of the UI already has
 * it), but for PS3 and PSP it answers the disc's ICON0: a 320x176 or 144x80
 * logo banner, not a sleeve. Drawn as a box, that was the giant blue slab that
 * opened a PS3 shelf until the card's media lookup caught up. So the cover is
 * decoded and measured first, and an aspect no box has sends us to the
 * scraped `box-front` instead, before the jacket ever turns to face you.
 *
 * One answer per game, shared by the swap (which holds a jacket edge-on until
 * it is known) and the Face (which draws it).
 */
import { jacket } from './dossier.js'

/**
 * The shapes a game box actually comes in. Measured on the box's 55 cached
 * covers: real fronts run 0.60 (portrait PS3 case) to 1.43 (landscape N64
 * carton); the banners sit at 1.80-1.82, with nothing in between.
 */
const RATIO_MIN = 0.5
const RATIO_MAX = 1.5
const plausible = (r) => r >= RATIO_MIN && r <= RATIO_MAX
const clamp = (r) => Math.max(RATIO_MIN, Math.min(RATIO_MAX, r))

/** Settled answers, readable synchronously so a box seen before mounts at its shape. */
const known = new Map()
const asked = new Map()
const key = (systemId, filename) => `${systemId}::${filename}`

/** Decode `src`: its aspect, 0 when the engine gives no size, null when it fails. */
const look = (src) => {
  const img = new Image()
  img.src = src
  if (!img.decode) return Promise.resolve(0)
  return img.decode().then(
    () => (img.naturalWidth && img.naturalHeight ? img.naturalWidth / img.naturalHeight : 0),
    () => null)
}

const settle = async (sdk, systemId, filename) => {
  const cover = jacket(systemId, filename)
  const r = await look(cover)
  if (r === null) return null                   // no cover: the Face prints its own
  if (!r || plausible(r)) return { src: cover, ratio: r || null }
  const scan = sdk.api.media.url(systemId, filename, 'box-front')
  const s = await look(scan)
  if (s === 0 || (s && plausible(s))) return { src: scan, ratio: s || null }
  // Every source is a banner: a box at the edge of the band beats one twice the stage.
  return { src: cover, ratio: clamp(r) }
}

/** What is already known about this game's front: the answer, or undefined. */
export const knownFront = (systemId, filename) => known.get(key(systemId, filename))

/**
 * The game's front, `{ src, ratio }` (ratio null when unmeasurable), or null
 * when it has no cover at all. A null is not remembered: a cover can be
 * scraped later, and the next look should see it.
 */
export const frontOf = (sdk, systemId, filename) => {
  const k = key(systemId, filename)
  if (known.has(k)) return Promise.resolve(known.get(k))
  if (!asked.has(k)) {
    asked.set(k, settle(sdk, systemId, filename).then((f) => {
      asked.delete(k)
      if (f) known.set(k, f)
      return f
    }))
  }
  return asked.get(k)
}
