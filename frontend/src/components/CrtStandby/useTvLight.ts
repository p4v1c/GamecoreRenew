import { useEffect, useRef } from 'react'
import { averageColor, lightFrom } from '../../lib/tvLight'

/** What the TV is showing, for the light it throws. */
export type LightSource =
  | { kind: 'picture'; el: HTMLVideoElement | HTMLImageElement | null }
  | { kind: 'snow' }
  | { kind: 'idle' }

const SAMPLE_MS = 250
const FRAME_MS = 50          // 20 updates a second is smooth for a slow glow
const EASE = 0.18
const SNOW = { rgb: [205, 215, 255], amount: 0.5 }
const IDLE = { rgb: [190, 200, 255], amount: 0.14 }
// Opacity of the light pass for a picture of luminance 0 and 1.
const LIGHT_FLOOR = 0.18
const LIGHT_SPAN = 0.62

const parse = (tint: string) => tint.slice(4, -1).split(',').map(Number)

/**
 * Tint the room's light pass with the picture's average colour, eased, with
 * a faint flicker. Writes two CSS variables on `root`; React never re-renders
 * for it. The sample is a 16x12 `drawImage`, four times a second.
 */
export function useTvLight(root: React.RefObject<HTMLElement>, source: LightSource,
                           reduced: boolean): void {
  const target = useRef({ rgb: IDLE.rgb, amount: IDLE.amount })
  const sourceRef = useRef(source)
  sourceRef.current = source

  useEffect(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 16; canvas.height = 12
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    const sample = () => {
      const s = sourceRef.current
      if (s.kind !== 'picture') { target.current = s.kind === 'snow' ? SNOW : IDLE; return }
      const el = s.el
      const ready = el instanceof HTMLVideoElement ? el.readyState >= 2 : !!el?.complete
      if (!el || !ctx || !ready) return
      try {
        ctx.drawImage(el, 0, 0, 16, 12)
        const { tint, amount } = lightFrom(averageColor(ctx.getImageData(0, 0, 16, 12).data))
        target.current = { rgb: parse(tint), amount }
      } catch { /* a frame that cannot be read keeps the last colour */ }
    }
    const now = { rgb: [...IDLE.rgb], amount: IDLE.amount }
    const paint = () => {
      const t = target.current
      now.rgb = now.rgb.map((c, i) => c + (t.rgb[i] - c) * EASE)
      now.amount += (t.amount - now.amount) * EASE
      const flicker = reduced ? 1 : 0.94 + Math.random() * 0.08
      const el = root.current
      if (!el) return
      el.style.setProperty('--tv-tint', `rgb(${now.rgb.map(Math.round).join(',')})`)
      el.style.setProperty('--tv-light', ((LIGHT_FLOOR + LIGHT_SPAN * now.amount) * flicker).toFixed(3))
    }
    sample()
    const sampler = setInterval(sample, SAMPLE_MS)
    const painter = setInterval(paint, reduced ? SAMPLE_MS : FRAME_MS)
    return () => { clearInterval(sampler); clearInterval(painter) }
  }, [root, reduced])
}
