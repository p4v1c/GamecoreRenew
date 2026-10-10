import { useEffect, useRef } from 'react'

const COUNT = 60
/** Pixels per second at 1080 lines, for the nearest motes; far ones are slower. */
const FALL = 26
/** Width of the side-to-side drift, in pixels, and how long one sway takes. */
const SWAY = 14
const SWAY_S = 7

interface Mote { x: number; y: number; z: number; phase: number; twinkle: number }

/** z is depth, 0 far to 1 near: near motes are bigger, brighter and fall faster. */
const spawn = (w: number, h: number, top = false): Mote => ({
  x: Math.random() * w,
  y: top ? -6 - Math.random() * h * 0.2 : Math.random() * h,
  z: Math.random(),
  phase: Math.random() * Math.PI * 2,
  twinkle: 0.6 + Math.random() * 1.4,
})

/**
 * Dust falling through the lamp light and the moonlight.
 *
 * It used to rise at a few hundredths of a pixel per frame, which on a TV read
 * as dust frozen in the picture. Now every mote falls, sways, and catches the
 * light as it turns; a mote that reaches the floor starts again above the top
 * edge. Warm on the lamp's side, cool on the window's. Driven by the frame
 * clock rather than a timer, so the speed does not depend on the frame rate.
 * Not drawn under reduced motion (the parent leaves it out).
 */
export function DustMotes() {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    let w = 0, h = 0
    const fit = () => { w = canvas.width = window.innerWidth; h = canvas.height = window.innerHeight }
    fit()
    const motes = Array.from({ length: COUNT }, () => spawn(w, h))
    let raf = 0
    let last = performance.now()
    const draw = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000)
      last = now
      const t = now / 1000
      const scale = h / 1080
      ctx.clearRect(0, 0, w, h)
      for (const m of motes) {
        m.y += FALL * scale * (0.35 + 0.65 * m.z) * dt
        if (m.y > h + 6) Object.assign(m, spawn(w, h, true))
        const x = m.x + Math.sin(t * (Math.PI * 2 / SWAY_S) + m.phase) * SWAY * scale * (0.5 + m.z)
        const glint = 0.55 + 0.45 * Math.sin(t * m.twinkle + m.phase)
        ctx.globalAlpha = (0.3 + 0.6 * m.z) * glint
        const tint = x < w * 0.4 ? '#ffe2c8' : '#e3e8ff'
        ctx.fillStyle = tint
        // A soft halo, so a mote reads as lit dust and not as a dead pixel.
        ctx.shadowColor = tint
        ctx.shadowBlur = 6 * scale * m.z
        ctx.beginPath()
        ctx.arc(x, m.y, (1.1 + 2.3 * m.z) * scale, 0, Math.PI * 2)
        ctx.fill()
      }
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    window.addEventListener('resize', fit)
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', fit) }
  }, [])
  return <canvas ref={ref} className="crt-dust" aria-hidden="true" />
}
