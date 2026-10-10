import { describe, it, expect } from 'vitest'
import { averageColor, lightFrom } from './tvLight'

describe('tvLight', () => {
  it('averages RGBA pixels and skips the transparent ones', () => {
    const px = new Uint8ClampedArray([
      255, 0, 0, 255,
      0, 0, 255, 255,
      9, 9, 9, 0,       // not drawn yet
    ])
    expect(averageColor(px)).toEqual({ r: 127.5, g: 0, b: 127.5 })
    expect(averageColor(new Uint8ClampedArray(8))).toEqual({ r: 0, g: 0, b: 0 })
  })

  it('keeps the hue of a dim scene and lowers only the amount', () => {
    const dim = lightFrom({ r: 40, g: 10, b: 0 })
    const bright = lightFrom({ r: 200, g: 50, b: 0 })
    expect(dim.tint).toBe('rgb(255,64,0)')
    expect(bright.tint).toBe(dim.tint)
    expect(dim.amount).toBeLessThan(bright.amount)
  })

  it('throws no light from a black picture', () => {
    expect(lightFrom({ r: 2, g: 3, b: 1 })).toEqual({ tint: 'rgb(255,255,255)', amount: 0 })
    expect(lightFrom({ r: 255, g: 255, b: 255 }).amount).toBeCloseTo(1)
  })
})
