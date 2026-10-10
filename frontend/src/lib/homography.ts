/**
 * Lay a flat element onto four points of a picture with one CSS `matrix3d`.
 *
 * The CRT standby draws a pre-rendered room and puts the game video on the TV
 * glass, which is seen at an angle: a perspective warp, not a rotate + skew.
 * `matrix3d` can express it exactly when its fourth row carries the projective
 * terms, so the video stays sharp and the GPU does the work.
 */

export type Point = [number, number]

/** The four corners in screen order. */
export interface Quad { tl: Point; tr: Point; br: Point; bl: Point }

/** Where a cover-fitted picture lands in the viewport, in pixels. */
export interface Rect { x: number; y: number; w: number; h: number }

/**
 * Name four corners by position rather than trusting their order.
 *
 * Blender writes them in the plane's vertex order (bottom-left, bottom-right,
 * top-left, top-right), which flips with the plane's rotation. Sorting holds
 * for any quad seen less than 45 degrees off square, which a TV on a stand is.
 */
export function quadFromCorners(points: Point[]): Quad {
  if (points.length !== 4) throw new Error('a quad needs 4 corners')
  const byY = [...points].sort((a, b) => a[1] - b[1])
  const [tl, tr] = byY.slice(0, 2).sort((a, b) => a[0] - b[0])
  const [bl, br] = byY.slice(2).sort((a, b) => a[0] - b[0])
  return { tl, tr, br, bl }
}

/** `object-fit: cover` for a picture of `iw`x`ih` in a `vw`x`vh` viewport. */
export function coverRect(vw: number, vh: number, iw: number, ih: number): Rect {
  const scale = Math.max(vw / iw, vh / ih)
  const w = iw * scale
  const h = ih * scale
  return { x: (vw - w) / 2, y: (vh - h) / 2, w, h }
}

/** A quad in 0..1 picture space, placed in viewport pixels. */
export function quadInRect(q: Quad, r: Rect): Quad {
  const at = ([u, v]: Point): Point => [r.x + u * r.w, r.y + v * r.h]
  return { tl: at(q.tl), tr: at(q.tr), br: at(q.br), bl: at(q.bl) }
}

/**
 * The CSS `matrix3d(...)` that maps a `w`x`h` box (origin top-left) onto `q`.
 *
 * Heckbert's square-to-quad projection, scaled to the box. Apply it with
 * `transform-origin: 0 0` on an absolutely positioned element at 0,0.
 */
export function matrix3dFor(w: number, h: number, q: Quad): string {
  const [x0, y0] = q.tl
  const [x1, y1] = q.tr
  const [x2, y2] = q.br
  const [x3, y3] = q.bl
  const dx1 = x1 - x2, dx2 = x3 - x2, dx3 = x0 - x1 + x2 - x3
  const dy1 = y1 - y2, dy2 = y3 - y2, dy3 = y0 - y1 + y2 - y3
  const den = dx1 * dy2 - dx2 * dy1
  const g = den ? (dx3 * dy2 - dx2 * dy3) / den : 0
  const k = den ? (dx1 * dy3 - dx3 * dy1) / den : 0
  const a = x1 - x0 + g * x1, b = x3 - x0 + k * x3
  const d = y1 - y0 + g * y1, e = y3 - y0 + k * y3
  // Unit square → box: divide the u terms by w and the v terms by h.
  const m = [
    a / w, d / w, 0, g / w,
    b / h, e / h, 0, k / h,
    0, 0, 1, 0,
    x0, y0, 0, 1,
  ]
  return `matrix3d(${m.map(n => +n.toPrecision(12)).join(',')})`
}
