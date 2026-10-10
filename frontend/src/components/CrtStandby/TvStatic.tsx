import { useEffect, useRef } from 'react'

const W = 160
const H = 125
const FPS_MS = 70

/**
 * Snow on the glass: between channels at full strength, soft when there is
 * nothing to show. A 160x125 canvas scaled up, redrawn 14 times a second only
 * while visible.
 */
export function TvStatic({ mode }: { mode: 'off' | 'on' | 'idle' }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const ctx = ref.current?.getContext('2d')
    if (!ctx || mode === 'off') return
    const img = ctx.createImageData(W, H)
    const draw = () => {
      const d = img.data
      for (let i = 0; i < d.length; i += 4) {
        const v = Math.random() * 255
        d[i] = v * 0.92; d[i + 1] = v * 0.95; d[i + 2] = v; d[i + 3] = 255
      }
      ctx.putImageData(img, 0, 0)
    }
    draw()
    const t = setInterval(draw, FPS_MS)
    return () => clearInterval(t)
  }, [mode])
  const cls = mode === 'on' ? ' is-on' : mode === 'idle' ? ' is-idle' : ''
  return <canvas ref={ref} width={W} height={H} className={`crt-tv-static${cls}`} aria-hidden="true" />
}
