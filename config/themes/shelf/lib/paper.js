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

// 90, not 60. The wall was drawn to sit UNDER a wide soft worm and read as
// texture; on its own it has to read as the pattern itself, and at 60 the
// motif came out half the size of the reference and twice as busy. 6 × 90 is a
// 540px tile, which puts roughly eight repeats across a 1080p screen — what
// the owner's reference shows.
const CELL = 90
const GRID = 6                    // 6 × 90 = a 540px tile
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
 *
 * The outline carries the wall now. It used to be a 34 %-opacity wash over the
 * wide worm below it, so 2.5px of visible band on each side was plenty; on its
 * own at full strength that reads as a hairline and the wall looks empty. The
 * band is the difference between the two strokes — (30 − 18) / 2 = 6px — held
 * at the same fraction of the cell as the reference, so the weight survives the
 * change of scale instead of thinning out with it.
 */
export const WALL_SOFT = tile(20411, 39, 0)
export const WALL_LINE = tile(77213, 30, 18)
export const WALL_TILE = CELL * GRID
