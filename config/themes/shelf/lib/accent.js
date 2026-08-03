/**
 * The colour the whole theme is wearing, and where it comes from.
 *
 * The signature of the reference capture is that nothing on screen has a fixed
 * accent: the wall, the badges and the focus ring all take their hue from the
 * box you are looking at, and cross-fade when you move. So the accent is not a
 * token — it is read out of the artwork, once per game, and cached.
 *
 * Two pieces:
 *   · `createAccentStore` — one value, shared by trees that never meet. The
 *     wall lives in `background`, the thing that decides the colour lives in
 *     `libraryView`; they are separate roots under the shell, so a plain
 *     subscription is the only way across. Nobody writes to the document.
 *   · `sample` — the reader. Draws the jacket into a 24px offscreen canvas and
 *     asks which hue owns it.
 */

/** Where a game with no readable artwork lands: GameCore's own violet. */
export const NEUTRAL = { h: 262, s: 42, l: 56 }

export const hexToHsl = (hex) => {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ''))
  if (!m) return null
  const n = parseInt(m[1], 16)
  return rgbToHsl((n >> 16) & 255, (n >> 8) & 255, n & 255)
}

function rgbToHsl(r, g, b) {
  const R = r / 255, G = g / 255, B = b / 255
  const max = Math.max(R, G, B), min = Math.min(R, G, B)
  const l = (max + min) / 2
  if (max === min) return { h: 0, s: 0, l: l * 100 }
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  const h = max === R ? ((G - B) / d + (G < B ? 6 : 0))
    : max === G ? (B - R) / d + 2
      : (R - G) / d + 4
  return { h: (h / 6) * 360, s: s * 100, l: l * 100 }
}

const cache = new Map()
let canvas = null

/**
 * The dominant hue of an image, as a colour the UI can actually wear.
 *
 * Not the average — averaging a box shot returns mud, every time, because the
 * cardboard, the Nintendo seal and the barcode outvote the artwork. This
 * buckets by hue instead and scores each bucket by saturation, which is what
 * picks ActRaiser's violet out of a picture that is mostly black lightning and
 * grey border.
 *
 * The result is clamped, not returned raw: a fully saturated 90% -light yellow
 * is a real answer for a Pikachu box and an unreadable one for a focus ring.
 *
 * The URL is one the host would have requested anyway — the same jacket the
 * `Cover` component is putting on screen a few pixels away — so this is a
 * second read of an image already in the browser cache, not a second download.
 * It is same-origin, so the canvas is never tainted.
 */
export const sample = (url) => {
  if (!url) return Promise.resolve(null)
  if (cache.has(url)) return Promise.resolve(cache.get(url))

  return new Promise((resolve) => {
    const img = new Image()
    img.decoding = 'async'
    img.onload = () => {
      let out = null
      try { out = read(img) } catch { out = null }
      cache.set(url, out)
      resolve(out)
    }
    img.onerror = () => { cache.set(url, null); resolve(null) }
    img.src = url
  })
}

const BUCKETS = 24

function read(img) {
  if (!canvas) canvas = document.createElement('canvas')
  canvas.width = 24
  canvas.height = 24
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return null
  ctx.drawImage(img, 0, 0, 24, 24)
  const { data } = ctx.getImageData(0, 0, 24, 24)

  const score = new Float64Array(BUCKETS)
  const sumS = new Float64Array(BUCKETS)
  const sumL = new Float64Array(BUCKETS)
  const count = new Float64Array(BUCKETS)

  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 200) continue
    const { h, s, l } = rgbToHsl(data[i], data[i + 1], data[i + 2])
    // Cardboard, ink and the Nintendo seal's white: present in every box shot,
    // and never the colour anyone would name the game by.
    if (s < 18 || l < 12 || l > 92) continue
    const b = Math.min(BUCKETS - 1, Math.floor((h / 360) * BUCKETS))
    score[b] += s / 100
    sumS[b] += s
    sumL[b] += l
    count[b] += 1
  }

  let best = -1, bestScore = 0
  for (let b = 0; b < BUCKETS; b++) {
    if (score[b] > bestScore) { bestScore = score[b]; best = b }
  }
  if (best < 0 || count[best] < 6) return null

  return {
    h: Math.round((best + 0.5) * (360 / BUCKETS)),
    s: clamp(sumS[best] / count[best], 38, 78),
    l: clamp(sumL[best] / count[best], 44, 62),
  }
}

const clamp = (v, lo, hi) => Math.round(Math.max(lo, Math.min(hi, v)))

const flatCache = new Map()

/**
 * Whether an image is a picture of nothing.
 *
 * Scrapers hand back chroma-key plates — a frame of pure #00FF00 where a scan
 * of the back of the box should be — and the theme has no way to tell, because
 * such a file is not broken: it downloads, it decodes, it draws. `onError`
 * never fires, so the printed reverse that exists precisely for a game with no
 * scan never gets its turn, and the shelf shows a slab of green instead. Nine
 * titles on this box are in that state across five different systems, so it is
 * the normal condition of a scraped library rather than one bad file.
 *
 * "Nothing" is defined by information, not by colour: quantise to a coarse
 * grid, and if 95% of the frame lands in one bucket there is no picture there
 * — no text, no screenshots, no cardboard edge. That catches green, magenta
 * and blue plates and flat fills of any colour without a list of them, and no
 * real cover comes close: even the plainest back has a barcode and a paragraph
 * of small print, which is enormous variance at 24px.
 *
 * Same canvas, same same-origin read, same cache-by-URL as `sample` above —
 * this is a second look at bytes the browser already has.
 */
export const flat = (url) => {
  if (!url) return Promise.resolve(false)
  if (flatCache.has(url)) return Promise.resolve(flatCache.get(url))

  return new Promise((resolve) => {
    const img = new Image()
    img.decoding = 'async'
    img.onload = () => {
      let out = false
      try { out = uniform(img) } catch { out = false }
      flatCache.set(url, out)
      resolve(out)
    }
    // A file that will not load is the case the theme already handles.
    img.onerror = () => { flatCache.set(url, false); resolve(false) }
    img.src = url
  })
}

function uniform(img) {
  if (!canvas) canvas = document.createElement('canvas')
  canvas.width = 24              // assigning the size also clears the canvas,
  canvas.height = 24             // so the previous image cannot bleed through
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return false
  ctx.drawImage(img, 0, 0, 24, 24)
  const { data } = ctx.getImageData(0, 0, 24, 24)

  const bins = new Map()
  let n = 0
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 200) continue
    const k = ((data[i] >> 4) << 8) | ((data[i + 1] >> 4) << 4) | (data[i + 2] >> 4)
    bins.set(k, (bins.get(k) || 0) + 1)
    n += 1
  }
  if (!n) return false

  let top = 0
  bins.forEach((v) => { if (v > top) top = v })
  return top / n >= 0.95
}

/** One value, many readers, no globals on the document. */
export const createAccentStore = (sdk) => {
  const { useState, useEffect } = sdk.ui
  let value = NEUTRAL
  const subs = new Set()

  const set = (next) => {
    const v = next || NEUTRAL
    if (v.h === value.h && v.s === value.s && v.l === value.l) return
    value = v
    subs.forEach((f) => f(v))
  }

  const use = () => {
    const [v, setV] = useState(value)
    useEffect(() => {
      setV(value)
      subs.add(setV)
      return () => { subs.delete(setV) }
    }, [])
    return v
  }

  return { set, use, get: () => value }
}

/** The three custom properties every surface of this theme reads. */
export const vars = (a) => ({
  '--acc-h': String(a.h),
  '--acc-s': `${a.s}%`,
  '--acc-l': `${a.l}%`,
})
