import { useEffect, useRef } from 'react'

const COUNT = 38
const FRAME_MS = 40

interface Mote { x: number; y: number; r: number; vx: number; vy: number; a: number; phase: number }

const spawn = (w: number, h: number): Mote => ({
  x: Math.random() * w, y: Math.random() * h,
  r: 0.8 + Math.random() * 1.6,
  vx: (Math.random() - 0.5) * 0.12, vy: -0.03 - Math.random() * 0.08,
  a: 0.25 + Math.random() * 0.4, phase: Math.random() * Math.PI * 2,
})

/** Dust drifting through the lamp light and the moonlight. Not drawn under reduced motion. */
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
    let tick = 0
    const draw = () => {
      tick++
      ctx.clearRect(0, 0, w, h)
      for (const m of motes) {
        m.x += m.vx + Math.sin(tick / 90 + m.phase) * 0.05
        m.y += m.vy
        if (m.y < -4) Object.assign(m, spawn(w, h), { y: h + 4 })
        if (m.x < -4) m.x = w + 4
        if (m.x > w + 4) m.x = -4
        ctx.globalAlpha = m.a * (0.7 + 0.3 * Math.sin(tick / 40 + m.phase))
        ctx.fillStyle = '#e8ecff'
        ctx.beginPath(); ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2); ctx.fill()
      }
    }
    const t = setInterval(draw, FRAME_MS)
    window.addEventListener('resize', fit)
    return () => { clearInterval(t); window.removeEventListener('resize', fit) }
  }, [])
  return <canvas ref={ref} className="crt-dust" aria-hidden="true" />
}
