/**
 * Boot splash — port of the "GameCore Boot" Claude Design component.
 *
 * Three coloured fragments (square / pill / play button) drift in, converge on
 * the centre, and collapse into a glowing core with a flash + shockwave; the
 * wordmark rises, then everything fades out and we hand over to the app.
 *
 * The animation is driven by one rAF loop that writes styles straight to the
 * DOM through refs — no per-frame React re-render, which keeps the boot smooth
 * on the box's modest GPU. Audio (a rising pad, then a Dmaj7 chime) is
 * synthesized on the app's shared AudioContext and honours the UI-sound
 * settings. Press ✕ / Enter / Space, or click, to fast-forward.
 */
import { useEffect, useRef } from 'react'
import { onGp } from '../hooks/useGamepad'
import { getAudioContext, soundSettings } from '../lib/sounds'

interface Props { onDone: () => void }

const ACCENT = '#B15BFF'

// Timeline (ms, at speed 1) — from the design
const T_PAD    = 850    // pad starts, fragments begin converging
const T_IMPACT = 2050   // convergence lands: flash, shockwave, chime
const T_END    = 3960   // hand over to the app (fade-out runs 3400→3940)

const clamp = (x: number, a = 0, b = 1) => Math.max(a, Math.min(b, x))
const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const eIO = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2)
const eO = (x: number) => 1 - Math.pow(1 - x, 3)

// Fragment paths: [startX, startY, startRot, startScale] → [endX, endY, endRot, endScale]
const FRAGMENTS = [
  { s: [-620, -300, -160, 1.8], n: [0, -104, 720, 0.66], c: '#5BC8FF' },
  { s: [640, 300, 140, 2.0],    n: [-90, 54, -720, 0.66], c: ACCENT },
  { s: [560, -360, -80, 1.7],   n: [90, 54, 700, 0.66],  c: '#FF5BA8' },
] as const

export default function Splash({ onDone }: Props) {
  const root = useRef<HTMLDivElement>(null)
  const splash = useRef<HTMLDivElement>(null)
  const bg = useRef<HTMLDivElement>(null)
  const group = useRef<HTMLDivElement>(null)
  const ring = useRef<HTMLDivElement>(null)
  const shock = useRef<HTMLDivElement>(null)
  const core = useRef<HTMLDivElement>(null)
  const flash = useRef<HTMLDivElement>(null)
  const wordmark = useRef<HTMLDivElement>(null)
  const frags = [useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null)]

  const onDoneRef = useRef(onDone)
  useEffect(() => { onDoneRef.current = onDone }, [onDone])

  useEffect(() => {
    let t = 0
    let last: number | null = null
    let rate = 1
    let raf = 0
    let padStarted = false
    let impacted = false
    let finished = false

    // ── audio ────────────────────────────────────────────────────────────────
    const vol = soundSettings.enabled ? soundSettings.volume / 100 : 0
    const ctx = vol > 0 ? getAudioContext() : null
    let reverbIn: ConvolverNode | null = null
    let pad: { g: GainNode; nodes: OscillatorNode[] } | null = null

    if (ctx) {
      const len = Math.floor(ctx.sampleRate * 1.8)
      const buf = ctx.createBuffer(2, len, ctx.sampleRate)
      for (let ch = 0; ch < 2; ch++) {
        const d = buf.getChannelData(ch)
        for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.6)
      }
      const conv = ctx.createConvolver()
      conv.buffer = buf
      const wet = ctx.createGain()
      wet.gain.value = 0.22 * vol
      conv.connect(wet)
      wet.connect(ctx.destination)
      reverbIn = conv
    }

    const startPad = () => {
      if (!ctx || !reverbIn) return
      const now = ctx.currentTime
      const g = ctx.createGain()
      g.gain.setValueAtTime(0.0001, now)
      g.gain.exponentialRampToValueAtTime(0.11 * vol, now + 1.15)
      const f = ctx.createBiquadFilter()
      f.type = 'lowpass'; f.Q.value = 7
      f.frequency.setValueAtTime(220, now)
      f.frequency.exponentialRampToValueAtTime(1200, now + 1.15)
      const o1 = ctx.createOscillator(); o1.type = 'sawtooth'
      o1.frequency.setValueAtTime(110, now); o1.frequency.linearRampToValueAtTime(164.81, now + 1.15)
      const o2 = ctx.createOscillator(); o2.type = 'sawtooth'; o2.detune.value = 9
      o2.frequency.setValueAtTime(110, now); o2.frequency.linearRampToValueAtTime(164.81, now + 1.15)
      const sub = ctx.createOscillator(); sub.type = 'sine'
      sub.frequency.setValueAtTime(55, now); sub.frequency.linearRampToValueAtTime(82.4, now + 1.15)
      const subg = ctx.createGain(); subg.gain.value = 0.5
      const lfo = ctx.createOscillator(); lfo.type = 'sine'; lfo.frequency.value = 5.5
      const lg = ctx.createGain(); lg.gain.value = 120
      o1.connect(f); o2.connect(f); sub.connect(subg); subg.connect(f)
      lfo.connect(lg); lg.connect(f.frequency)
      f.connect(g); g.connect(ctx.destination); g.connect(reverbIn)
      const nodes = [o1, o2, sub, lfo]
      nodes.forEach(n => n.start(now))
      pad = { g, nodes }
    }

    const stopPad = () => {
      if (!ctx || !pad) return
      const now = ctx.currentTime
      const { g, nodes } = pad
      g.gain.cancelScheduledValues(now)
      g.gain.setValueAtTime(Math.max(0.0001, g.gain.value), now)
      g.gain.exponentialRampToValueAtTime(0.0001, now + 0.22)
      nodes.forEach(o => { try { o.stop(now + 0.26) } catch { /* already stopped */ } })
      pad = null
    }

    const playChime = () => {
      if (!ctx || !reverbIn) return
      const t0 = ctx.currentTime
      const bus = ctx.createGain(); bus.gain.value = 0.9
      bus.connect(ctx.destination); bus.connect(reverbIn)
      const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 6500
      lp.connect(bus)
      const chord = [587.33, 739.99, 880.0, 1108.73]   // Dmaj7
      chord.forEach((fr, i) => {
        const at = t0 + i * 0.028
        const g = ctx.createGain()
        g.gain.setValueAtTime(0.0001, at)
        g.gain.exponentialRampToValueAtTime(Math.max(0.05, 0.22 - i * 0.03) * vol, at + 0.008)
        g.gain.exponentialRampToValueAtTime(0.0001, at + 1.6)
        const o = ctx.createOscillator(); o.type = 'sine'; o.frequency.value = fr
        const tri = ctx.createOscillator(); tri.type = 'triangle'; tri.frequency.value = fr / 2
        const tg = ctx.createGain(); tg.gain.value = 0.18
        o.connect(g); tri.connect(tg); tg.connect(g); g.connect(lp)
        o.start(at); tri.start(at); o.stop(at + 1.7); tri.stop(at + 1.7)
      })
      // sparkle
      const s = ctx.createGain()
      s.gain.setValueAtTime(0.0001, t0)
      s.gain.exponentialRampToValueAtTime(0.06 * vol, t0 + 0.01)
      s.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.9)
      const so = ctx.createOscillator(); so.type = 'sine'; so.frequency.value = 2349.32
      so.connect(s); s.connect(lp); so.start(t0); so.stop(t0 + 1.0)
      // impact thump
      const th = ctx.createGain()
      th.gain.setValueAtTime(0.5 * vol, t0)
      th.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.5)
      const tho = ctx.createOscillator(); tho.type = 'sine'
      tho.frequency.setValueAtTime(160, t0); tho.frequency.exponentialRampToValueAtTime(50, t0 + 0.4)
      tho.connect(th); th.connect(ctx.destination); tho.start(t0); tho.stop(t0 + 0.55)
    }

    // ── frame ────────────────────────────────────────────────────────────────
    const draw = () => {
      const fin = clamp(t / 260)
      const conv = clamp((t - T_PAD) / 1200)
      const cp = eIO(conv)
      const flashRaw = t < T_IMPACT ? 0 : Math.max(0, 1 - (t - T_IMPACT) / 210)
      const shockP = clamp((t - T_IMPACT) / 600)
      const showShock = t >= T_IMPACT && t < T_IMPACT + 630
      const coreP = clamp((t - T_IMPACT) / 240)
      const pop = t >= T_IMPACT ? Math.sin(clamp((t - T_IMPACT) / 300) * Math.PI) * 0.1 : 0
      const breathe = t > T_IMPACT + 100 ? Math.sin((t - T_IMPACT - 100) / 560) * 0.016 : 0
      const wp = clamp((t - 2150) / 520)
      const fo = clamp((t - 3400) / 540)
      const ringIn = clamp((cp - 0.55) / 0.45)
      const R = 122

      if (splash.current) splash.current.style.opacity = String(1 - fo)
      if (bg.current) bg.current.style.opacity = String(conv * 0.16)
      if (group.current) group.current.style.transform = `translate(-50%,-50%) scale(${1 + breathe + pop * 0.3})`

      FRAGMENTS.forEach((f, i) => {
        const el = frags[i].current
        if (!el) return
        const [sx, sy, sr, ssc] = f.s
        const [nx, ny, nr, nsc] = f.n
        const fa = 1 - cp
        const x = lerp(sx, nx, cp) + Math.sin(t / 360 + i * 2) * 24 * fa
        const y = lerp(sy, ny, cp) + Math.cos(t / 300 + i * 1.7) * 24 * fa
        const rot = lerp(sr, nr, cp)
        const sc = lerp(ssc, nsc, cp) * (1 + pop)
        const glow = 6 + conv * 22 + (t >= T_IMPACT ? 18 : 0)
        el.style.opacity = String(fin)
        el.style.transform = `translate(-50%,-50%) translate(${x}px,${y}px) rotate(${rot}deg) scale(${sc})`
        el.style.filter = `drop-shadow(0 0 ${glow}px ${f.c})`
      })

      if (ring.current) {
        ring.current.style.opacity = String(ringIn * 0.5 + coreP * 0.15)
        ring.current.style.transform = `scale(${lerp(0.7, 1, eO(ringIn))})`
        ring.current.style.boxShadow = `0 0 ${18 + coreP * 30}px ${ACCENT}55, inset 0 0 20px ${ACCENT}22`
        ring.current.style.width = ring.current.style.height = R * 2 + 'px'
        ring.current.style.marginLeft = ring.current.style.marginTop = -R + 'px'
      }
      if (shock.current) {
        shock.current.style.opacity = String(showShock ? (1 - shockP) * 0.8 : 0)
        shock.current.style.transform = `scale(${0.5 + eO(shockP) * 4.2})`
      }
      if (core.current) {
        core.current.style.opacity = String(coreP)
        core.current.style.transform = `rotate(45deg) scale(${eO(coreP) * (1 + pop * 0.6)})`
        core.current.style.boxShadow = `0 0 ${24 + coreP * 26}px ${ACCENT}, 0 0 60px ${ACCENT}88`
      }
      if (flash.current) flash.current.style.opacity = String(0.95 * flashRaw * flashRaw)
      if (wordmark.current) {
        wordmark.current.style.opacity = String(wp * (1 - fo))
        wordmark.current.style.transform = `translate(-50%,0) translateY(${(1 - eO(wp)) * 16}px)`
      }
    }

    const finish = () => {
      if (finished) return
      finished = true
      cancelAnimationFrame(raf)
      stopPad()
      onDoneRef.current()
    }

    const loop = (ts: number) => {
      if (last == null) last = ts
      const dt = Math.min(64, ts - last)
      last = ts
      t += dt * rate

      if (t >= T_PAD && !padStarted) { padStarted = true; startPad() }
      if (t >= T_IMPACT && !impacted) { impacted = true; stopPad(); playChime() }
      if (t >= T_END) { finish(); return }

      draw()
      raf = requestAnimationFrame(loop)
    }

    // Fast-forward instead of cutting: never looks broken mid-animation
    const skip = () => { if (!finished) { rate = 4; padStarted = true; stopPad() } }

    const onKey = (e: KeyboardEvent) => {
      if (e.repeat) return
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); skip() }
    }
    window.addEventListener('keydown', onKey)
    root.current?.addEventListener('click', skip)
    const offGp = onGp('gp:confirm', skip)

    draw()
    raf = requestAnimationFrame(loop)

    return () => {
      cancelAnimationFrame(raf)
      stopPad()
      window.removeEventListener('keydown', onKey)
      root.current?.removeEventListener('click', skip)
      offGp()
    }
  }, [])

  const fragBase: React.CSSProperties = { position: 'absolute', left: 0, top: 0, opacity: 0 }

  return (
    <div
      ref={root}
      style={{
        position: 'fixed', inset: 0, zIndex: 9000, overflow: 'hidden',
        background: '#050409', cursor: 'pointer', userSelect: 'none',
        fontFamily: "'Space Grotesk','Outfit',system-ui,sans-serif",
      }}
    >
      <div ref={splash} style={{ position: 'absolute', inset: 0 }}>
        <div ref={bg} style={{
          position: 'absolute', inset: 0, opacity: 0, pointerEvents: 'none',
          background: `radial-gradient(circle at 50% 46%, ${ACCENT}, transparent 62%)`,
        }} />

        <div ref={group} style={{ position: 'absolute', left: '50%', top: '50%' }}>
          <div ref={ring} style={{
            position: 'absolute', left: 0, top: 0, borderRadius: '50%',
            border: `1.5px solid ${ACCENT}`, opacity: 0, pointerEvents: 'none',
          }} />
          <div ref={shock} style={{
            position: 'absolute', left: 0, top: 0, width: 80, height: 80,
            marginLeft: -40, marginTop: -40, borderRadius: '50%',
            border: `2px solid ${ACCENT}`, opacity: 0, pointerEvents: 'none',
            boxShadow: `0 0 30px ${ACCENT}66`,
          }} />

          {/* Fragment 1 — square */}
          <div ref={frags[0]} style={fragBase}>
            <div style={{
              width: 78, height: 78, borderRadius: 3,
              background: 'linear-gradient(150deg,#a9e8ff,#5BC8FF 55%,#2e9fe0)',
              boxShadow: 'inset 0 0 0 2px rgba(255,255,255,.4), inset -7px -7px 0 rgba(0,0,0,.16)',
            }} />
          </div>

          {/* Fragment 2 — pill */}
          <div ref={frags[1]} style={fragBase}>
            <div style={{
              width: 96, height: 70, borderRadius: '38px/34px',
              background: 'linear-gradient(150deg,#dcb0ff,#B15BFF 55%,#8a34e0)',
              boxShadow: 'inset 0 0 0 2px rgba(255,255,255,.34)',
            }} />
          </div>

          {/* Fragment 3 — play button */}
          <div ref={frags[2]} style={fragBase}>
            <div style={{
              position: 'relative', width: 112, height: 66, borderRadius: 9,
              background: 'linear-gradient(150deg,#ffb0d8,#FF5BA8 55%,#e0348a)',
              boxShadow: 'inset 0 0 0 2px rgba(255,255,255,.32)',
            }}>
              <div style={{
                position: 'absolute', left: '50%', top: '50%',
                transform: 'translate(-40%,-50%)', width: 0, height: 0,
                borderLeft: '17px solid rgba(255,255,255,.94)',
                borderTop: '11px solid transparent',
                borderBottom: '11px solid transparent',
              }} />
            </div>
          </div>

          <div ref={core} style={{
            position: 'absolute', left: 0, top: 0, width: 46, height: 46,
            marginLeft: -23, marginTop: -23, borderRadius: 12, opacity: 0,
            background: `radial-gradient(circle at 50% 40%, #fff, ${ACCENT} 55%)`,
          }} />
        </div>

        <div ref={wordmark} style={{
          position: 'absolute', left: '50%', top: '60%', opacity: 0,
          transform: 'translate(-50%,0)', whiteSpace: 'nowrap',
          fontSize: 'clamp(28px,4.6vw,62px)', fontWeight: 700, letterSpacing: '.42em',
          color: '#fff', textShadow: `0 0 26px ${ACCENT}`, paddingLeft: '.42em',
        }}>
          GAMECORE
        </div>

        <div ref={flash} style={{
          position: 'absolute', inset: 0, opacity: 0, pointerEvents: 'none',
          background: `radial-gradient(circle at 50% 46%, #ffffff, ${ACCENT}cc 40%, transparent 72%)`,
          mixBlendMode: 'screen',
        }} />
      </div>
    </div>
  )
}
