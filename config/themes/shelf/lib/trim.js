/**
 * App logos, cropped to the ink.
 *
 * Every app tile on the home row is the same white square with the pack's logo
 * inside it, and the logos are not drawn on the same canvas. YouTube's mark
 * fills its file; Twitch's sits in the middle 60 % of a 980px square. Fitted
 * into the same box, one looked twice the size of the other, and the row read
 * as careless rather than as a set.
 *
 * The fix belongs at runtime, not in the packs: a pack's logo is the pack
 * author's file, used by every theme, and an app added next month will arrive
 * with whatever padding its author chose. So the transparent margin is measured
 * here — the alpha channel's bounding box, on a downscaled copy — and the
 * picture is redrawn without it.
 *
 * One canvas pass per logo URL, cached for the page. The files are the host's
 * own `/assets/logos/…`, same-origin, so the canvas is never tainted; if it ever
 * were, or the image fails, the original URL is used as it is.
 */

/** URL in, cropped data URL out (or the original on any failure). */
const done = new Map()
const pending = new Map()

/** Longest side the measurement is taken at. Plenty for a 112px tile. */
const SIDE = 256
/** Alpha below this counts as empty: anti-aliasing haze is not ink. */
const ALPHA_MIN = 12

export const trimmed = (url) => {
  if (!url) return Promise.resolve(null)
  if (done.has(url)) return Promise.resolve(done.get(url))
  if (pending.has(url)) return pending.get(url)

  const job = new Promise((resolve) => {
    const img = new Image()
    img.decoding = 'async'
    img.onload = () => {
      let out = url
      try { out = crop(img) || url } catch { out = url }
      done.set(url, out)
      pending.delete(url)
      resolve(out)
    }
    img.onerror = () => { done.set(url, url); pending.delete(url); resolve(url) }
    img.src = url
  })
  pending.set(url, job)
  return job
}

/** Synchronous peek, so a tile already measured never draws the padded file first. */
export const trimmedNow = (url) => done.get(url) || null

function crop(img) {
  const w0 = img.naturalWidth, h0 = img.naturalHeight
  if (!w0 || !h0) return null
  const k = Math.min(1, SIDE / Math.max(w0, h0))
  const w = Math.max(1, Math.round(w0 * k)), h = Math.max(1, Math.round(h0 * k))

  const c = document.createElement('canvas')
  c.width = w; c.height = h
  const ctx = c.getContext('2d', { willReadFrequently: true })
  if (!ctx) return null
  ctx.drawImage(img, 0, 0, w, h)
  const { data } = ctx.getImageData(0, 0, w, h)

  let x0 = w, y0 = h, x1 = -1, y1 = -1
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (data[(y * w + x) * 4 + 3] < ALPHA_MIN) continue
      if (x < x0) x0 = x
      if (x > x1) x1 = x
      if (y < y0) y0 = y
      if (y > y1) y1 = y
    }
  }
  if (x1 < 0) return null                       // fully transparent: leave it alone
  // An opaque logo (no margin to remove) is already as large as it can be.
  if (x0 === 0 && y0 === 0 && x1 === w - 1 && y1 === h - 1) return img.src

  // Back to source pixels, with one pixel of slack so an edge is not shaved.
  const sx = Math.max(0, Math.floor((x0 - 1) / k)), sy = Math.max(0, Math.floor((y0 - 1) / k))
  const sw = Math.min(w0 - sx, Math.ceil((x1 - x0 + 3) / k))
  const sh = Math.min(h0 - sy, Math.ceil((y1 - y0 + 3) / k))
  const scale = Math.min(1, 512 / Math.max(sw, sh))
  const out = document.createElement('canvas')
  out.width = Math.max(1, Math.round(sw * scale))
  out.height = Math.max(1, Math.round(sh * scale))
  out.getContext('2d').drawImage(img, sx, sy, sw, sh, 0, 0, out.width, out.height)
  return out.toDataURL('image/png')
}
