/**
 * The colour a TV throws on the room, from a few pixels of what it shows.
 *
 * The CRT standby draws the video's average colour every quarter second into
 * a tiny canvas and tints the room's light pass with it. These are the pure
 * halves: average the pixels, then split the result into a hue (the tint) and
 * an amount (how much light).
 */

export interface Rgb { r: number; g: number; b: number }

/** Mean colour of RGBA pixels. Transparent pixels (not drawn yet) are skipped. */
export function averageColor(data: ArrayLike<number>): Rgb {
  let r = 0, g = 0, b = 0, n = 0
  for (let i = 0; i + 3 < data.length; i += 4) {
    if (data[i + 3] === 0) continue
    r += data[i]; g += data[i + 1]; b += data[i + 2]; n++
  }
  if (!n) return { r: 0, g: 0, b: 0 }
  return { r: r / n, g: g / n, b: b / n }
}

/** Below this the picture is black and its hue is noise. */
const DARK = 6

/**
 * Hue at full brightness, and the light as 0..1 (relative luminance).
 *
 * The tint is normalised so a dim red scene still reads red on the wall; the
 * amount is what makes a dark scene throw less light than a bright one.
 */
export function lightFrom(c: Rgb): { tint: string; amount: number } {
  const max = Math.max(c.r, c.g, c.b)
  if (max < DARK) return { tint: 'rgb(255,255,255)', amount: 0 }
  const s = 255 / max
  const tint = `rgb(${Math.round(c.r * s)},${Math.round(c.g * s)},${Math.round(c.b * s)})`
  const amount = (0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b) / 255
  return { tint, amount: Math.min(1, Math.max(0, amount)) }
}
