/**
 * The boot animation.
 *
 * Three coloured fragments drift in, converge, and collapse into a glowing core
 * with a flash and a shockwave; the wordmark rises and the whole thing fades
 * out. A port of the host's Splash.tsx, which is the point — it is the surface
 * with the most host-only machinery in it, so if a theme can express this one
 * the SDK is in reasonable shape.
 *
 * Three things it proves:
 *
 * 1. **A theme can animate at 60 fps without re-rendering.** One rAF loop
 *    writing straight to the DOM through refs, no per-frame React. The box has
 *    a modest GPU and the dashboard is mounting underneath.
 * 2. **A theme can synthesize audio on the host's context** and stay inside the
 *    player's sound setting — read here, once, before anything is scheduled.
 * 3. **A theme does not decide when booting ends.** `onDone` is the host's, and
 *    a 20 s watchdog sits behind it. ✕ fast-forwards rather than cutting: a
 *    hard cut mid-animation always looks like a crash.
 *
 * No z-index anywhere in this file. The host mounts the splash inside its own
 * layer at 9000 — the default Splash sets that on itself, which is a thing only
 * the host is allowed to do, and a themed splash that tried came up UNDER the
 * dashboard.
 */
const ACCENT = '#B15BFF'

const T_PAD = 850      // fragments start converging, pad comes in
const T_IMPACT = 2050  // convergence lands: flash, shockwave, chime
const T_END = 3960     // hand back to the host

const FRAGMENTS = [
  { s: [-620, -300, -160, 1.8], n: [0, -104, 720, 0.66], c: '#5BC8FF' },
  { s: [640, 300, 140, 2.0], n: [-90, 54, -720, 0.66], c: ACCENT },
  { s: [560, -360, -80, 1.7], n: [90, 54, 700, 0.66], c: '#FF5BA8' },
]

const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x))
const lerp = (a, b, t) => a + (b - a) * t
const eIO = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2)
const eO = (x) => 1 - Math.pow(1 - x, 3)

export const createSplash = (sdk) => {
  const { html, useEffect, useRef } = sdk.ui

  return ({ onDone }) => {
    const root = useRef(null)
    const bg = useRef(null)
    const group = useRef(null)
    const ring = useRef(null)
    const shock = useRef(null)
    const core = useRef(null)
    const flash = useRef(null)
    const word = useRef(null)
    const f0 = useRef(null)
    const f1 = useRef(null)
    const f2 = useRef(null)

    const doneRef = useRef(onDone)
    useEffect(() => { doneRef.current = onDone }, [onDone])

    useEffect(() => {
      const frags = [f0, f1, f2]
      // Negative start = hold the black first frame. At cold boot the display
      // path is still dark when we mount, so without this the animation plays
      // against a screen nobody can see and the player's first glimpse is the
      // middle of it. Every phase below clamps at t <= 0, so nothing moves —
      // and skip() still fast-forwards through the hold at 4x.
      let t = -sdk.system.splashHoldMs
      let last = null
      let rate = 1
      let raf = 0
      let padStarted = false
      let impacted = false
      let finished = false

      // Read once, before anything is scheduled. The setting can change while
      // the box is booting and re-reading mid-animation would leave half a
      // chord playing after the player muted it.
      const vol = sdk.system.sound.enabled ? sdk.system.sound.volume : 0
      const ctx = vol > 0 ? sdk.system.getAudioContext() : null
      let pad = null

      const startPad = () => {
        if (!ctx) return
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
        o1.connect(f); o2.connect(f); f.connect(g); g.connect(ctx.destination)
        const nodes = [o1, o2]
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

      const chime = () => {
        if (!ctx) return
        const t0 = ctx.currentTime
        const bus = ctx.createGain(); bus.gain.value = 0.9
        bus.connect(ctx.destination)
        const chord = [587.33, 739.99, 880.0, 1108.73]   // Dmaj7
        chord.forEach((fr, i) => {
          const at = t0 + i * 0.028
          const g = ctx.createGain()
          g.gain.setValueAtTime(0.0001, at)
          g.gain.exponentialRampToValueAtTime(Math.max(0.05, 0.22 - i * 0.03) * vol, at + 0.008)
          g.gain.exponentialRampToValueAtTime(0.0001, at + 1.6)
          const o = ctx.createOscillator(); o.type = 'sine'; o.frequency.value = fr
          o.connect(g); g.connect(bus)
          o.start(at); o.stop(at + 1.7)
        })
      }

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

        // Fade the ROOT, black backdrop included, so the dashboard mounting
        // underneath shows through progressively — a real cross-fade rather
        // than content fading on black and then a hard cut at unmount.
        if (root.current) root.current.style.opacity = String(1 - fo)
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
          const sc = lerp(ssc, nsc, cp) * (1 + pop)
          const glow = 6 + conv * 22 + (t >= T_IMPACT ? 18 : 0)
          el.style.opacity = String(fin)
          el.style.transform = `translate(-50%,-50%) translate(${x}px,${y}px) rotate(${lerp(sr, nr, cp)}deg) scale(${sc})`
          el.style.filter = `drop-shadow(0 0 ${glow}px ${f.c})`
        })

        if (ring.current) {
          ring.current.style.opacity = String(ringIn * 0.5 + coreP * 0.15)
          ring.current.style.transform = `scale(${lerp(0.7, 1, eO(ringIn))})`
          ring.current.style.width = ring.current.style.height = `${R * 2}px`
          ring.current.style.marginLeft = ring.current.style.marginTop = `${-R}px`
        }
        if (shock.current) {
          shock.current.style.opacity = String(showShock ? (1 - shockP) * 0.8 : 0)
          shock.current.style.transform = `scale(${0.5 + eO(shockP) * 4.2})`
        }
        if (core.current) {
          core.current.style.opacity = String(coreP)
          core.current.style.transform = `rotate(45deg) scale(${eO(coreP) * (1 + pop * 0.6)})`
        }
        if (flash.current) flash.current.style.opacity = String(0.95 * flashRaw * flashRaw)
        if (word.current) {
          word.current.style.opacity = String(wp * (1 - fo))
          word.current.style.transform = `translate(-50%,0) translateY(${(1 - eO(wp)) * 16}px)`
        }
      }

      const finish = () => {
        if (finished) return
        finished = true
        cancelAnimationFrame(raf)
        stopPad()
        // The host's, always. A theme that forgets this leaves the box on its
        // title card until the watchdog fires.
        doneRef.current()
      }

      const loop = (ts) => {
        if (last == null) last = ts
        const dt = Math.min(64, ts - last)
        last = ts
        t += dt * rate

        if (t >= T_PAD && !padStarted) { padStarted = true; startPad() }
        if (t >= T_IMPACT && !impacted) { impacted = true; stopPad(); chime() }
        if (t >= T_END) { finish(); return }

        draw()
        raf = requestAnimationFrame(loop)
      }

      // Fast-forward rather than cut — a cut mid-animation reads as a crash.
      const skip = () => { if (!finished) { rate = 4; padStarted = true; stopPad() } }
      const offGp = sdk.input.onGp('gp:confirm', skip)
      const el = root.current
      el?.addEventListener('click', skip)

      draw()
      raf = requestAnimationFrame(loop)

      return () => {
        cancelAnimationFrame(raf)
        stopPad()
        offGp()
        el?.removeEventListener('click', skip)
      }
    }, [])

    return html`
      <div class="dr-splash" ref=${root}>
        <div class="dr-splash-bg" ref=${bg} />
        <div class="dr-splash-group" ref=${group}>
          <div class="dr-splash-ring" ref=${ring} />
          <div class="dr-splash-shock" ref=${shock} />
          <div class="dr-frag" ref=${f0}><div class="dr-frag-square" /></div>
          <div class="dr-frag" ref=${f1}><div class="dr-frag-pill" /></div>
          <div class="dr-frag" ref=${f2}>
            <div class="dr-frag-play"><div class="dr-frag-tri" /></div>
          </div>
          <div class="dr-splash-core" ref=${core} />
        </div>
        <div class="dr-splash-word" ref=${word}>GAMECORE</div>
        <div class="dr-splash-flash" ref=${flash} />
      </div>`
  }
}
