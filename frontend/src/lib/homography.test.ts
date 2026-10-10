import { describe, it, expect } from 'vitest'
import { coverRect, matrix3dFor, quadFromCorners, quadInRect, type Point, type Quad } from './homography'
import corners from '../assets/standby/room-screen.json'

/** Apply a CSS matrix3d (column-major) to a 2D point, with the perspective divide. */
function project(css: string, x: number, y: number): Point {
  const m = css.slice('matrix3d('.length, -1).split(',').map(Number)
  const X = m[0] * x + m[4] * y + m[12]
  const Y = m[1] * x + m[5] * y + m[13]
  const W = m[3] * x + m[7] * y + m[15]
  return [X / W, Y / W]
}

const near = (a: Point, b: Point) => {
  expect(a[0]).toBeCloseTo(b[0], 4)
  expect(a[1]).toBeCloseTo(b[1], 4)
}

describe('homography', () => {
  it('names the corners by position, whatever order Blender wrote them in', () => {
    const q = quadFromCorners(corners as Point[])
    // The plane's vertex order is bottom-left, bottom-right, top-left, top-right.
    expect(q).toEqual({ bl: corners[0], br: corners[1], tl: corners[2], tr: corners[3] })
  })

  it('maps each corner of the box onto the quad, including perspective', () => {
    const q: Quad = { tl: [100, 50], tr: [400, 80], br: [380, 300], bl: [120, 260] }
    const css = matrix3dFor(640, 480, q)
    near(project(css, 0, 0), q.tl)
    near(project(css, 640, 0), q.tr)
    near(project(css, 640, 480), q.br)
    near(project(css, 0, 480), q.bl)
    // Not affine: the centre of the box is not the average of the corners.
    const [cx] = project(css, 320, 240)
    expect(Math.abs(cx - 250)).toBeGreaterThan(0.5)
  })

  it('is a plain translate+scale for a rectangle', () => {
    const css = matrix3dFor(200, 100, { tl: [10, 20], tr: [410, 20], br: [410, 220], bl: [10, 220] })
    expect(css).toBe('matrix3d(2,0,0,0,0,2,0,0,0,0,1,0,10,20,0,1)')
  })

  it('places the TV on a cover-fitted plate, cropped on a 4:3 screen', () => {
    expect(coverRect(1920, 1080, 1920, 1080)).toEqual({ x: 0, y: 0, w: 1920, h: 1080 })
    const r = coverRect(1440, 1080, 1920, 1080)
    expect(r).toEqual({ x: -240, y: 0, w: 1920, h: 1080 })
    const q = quadInRect(quadFromCorners(corners as Point[]), r)
    near(q.tl, [0.47995 * 1920 - 240, 0.23971 * 1080])
  })
})
