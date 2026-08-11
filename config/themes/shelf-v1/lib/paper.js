/**
 * The wall the shelf stands against.
 *
 * The reference capture has a papered wall of interlocking worms behind the
 * boxes, and it retints itself to whatever box is facing you. That rules out
 * shipping the pattern as a coloured PNG: the colour has to be a CSS property
 * so it can transition, which means the pattern has to be a *mask* and the
 * colour a plain `background-color` underneath it.
 *
 * The tile is Truchet: every cell holds two quarter-turns that meet the cell's
 * edges at their midpoints, so any arrangement of any orientation is
 * continuous — the tile repeats seamlessly in both axes with no seam to hide.
 * Written once here as a data URI, at module scope, so it costs one string for
 * the life of the theme and nothing per frame.
 *
 * Quarter-turns are cubic Béziers rather than `A` arcs on purpose: the control
 * points make the tangents at the edge midpoints exactly perpendicular to the
 * edge, which is what lets two neighbouring cells join without a kink. An arc
 * would need a sweep flag, and the wrong one is a bulge nobody notices until
 * the whole wall looks slightly wrong.
 */

const CELL = 60
const GRID = 6                    // 6 × 60 = a 360px tile
const K = 0.5523 * (CELL / 2)     // circle constant — quarter-turn control offset

/** Deterministic, so the wall is the same wall on every boot. */
const rng = (seed) => () => {
  seed = (seed * 1664525 + 1013904223) % 4294967296
  return seed / 4294967296
}

const cell = (ox, oy, flip) => {
  const h = CELL / 2
  return flip
    // corners top-right and bottom-left
    ? `M${ox + h},${oy}C${ox + h},${oy + K} ${ox + CELL - K},${oy + h} ${ox + CELL},${oy + h}` +
      `M${ox},${oy + h}C${ox + K},${oy + h} ${ox + h},${oy + CELL - K} ${ox + h},${oy + CELL}`
    // corners top-left and bottom-right
    : `M${ox},${oy + h}C${ox + K},${oy + h} ${ox + h},${oy + K} ${ox + h},${oy}` +
      `M${ox + h},${oy + CELL}C${ox + h},${oy + CELL - K} ${ox + CELL - K},${oy + h} ${ox + CELL},${oy + h}`
}

/**
 * @param seed     which wall you get — same number, same wall
 * @param outer    stroke width of the worm
 * @param inner    stroke width of the hole punched through it; 0 draws it solid
 */
const tile = (seed, outer, inner) => {
  const next = rng(seed)
  let d = ''
  for (let y = 0; y < GRID; y++) {
    for (let x = 0; x < GRID; x++) d += cell(x * CELL, y * CELL, next() > 0.5)
  }
  const size = CELL * GRID
  // An SVG mask inside the tile is what turns a stroke into an outline: white
  // paints the worm, black punches its middle back out. A single stroke cannot
  // erase itself.
  const body = inner > 0
    ? `<defs><path id="w" d="${d}" fill="none" stroke-linecap="round"/>` +
      `<mask id="m"><use href="#w" stroke="#fff" stroke-width="${outer}"/>` +
      `<use href="#w" stroke="#000" stroke-width="${inner}"/></mask></defs>` +
      `<rect width="${size}" height="${size}" fill="#fff" mask="url(#m)"/>`
    : `<path d="${d}" fill="none" stroke="#fff" stroke-width="${outer}" stroke-linecap="round"/>`

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">${body}</svg>`
  return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`
}

/**
 * Two layers, deliberately out of register: a wide soft worm and a narrow
 * outlined one drawn from a different seed. One layer read as wallpaper; two
 * read as a wall someone chose.
 */
export const WALL_SOFT = tile(20411, 26, 0)
export const WALL_LINE = tile(77213, 15, 10)
export const WALL_TILE = CELL * GRID
