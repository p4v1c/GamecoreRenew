/**
 * The launch transition: the screen closes into a turning iris, then the game
 * takes the display.
 *
 * Why it is not in `decor`, which is the slot meant for painting over
 * everything: the shell unmounts that layer the moment a session opens —
 *
 *     {!sessionGameKey && <div style={{ zIndex: 400 }}><Decor /></div>}
 *
 * — which is the exact instant this animation has to start. So the veil is a
 * sibling of the shell in the theme's own tree instead. That is the one place
 * a theme may stack something itself: it covers the theme's whole frontend,
 * which the theme replaced entirely, so it cannot paint over a screen it does
 * not own.
 *
 * It follows `sessionGameKey` and nothing else, which is what makes it safe:
 * that flag is set for a game and for an app alike (defaults.launchApp calls
 * the same setSession), and it is cleared on exit *and on failure*. A veil
 * that closed on launch but had no rule for failing would leave a black screen
 * over a box that is working perfectly well — the emulator that never started
 * is annoying, a launcher that looks dead is worse.
 *
 * There is no delay before the launch, on purpose. An emulator takes one to
 * fifteen seconds to put a window up and this runs in seven hundred
 * milliseconds, so the two overlap for free. Animating first and launching
 * after would buy nothing and cost the player half a second every time.
 */

// Long enough to feel deliberate, short enough to always be finished before the
// game arrives. That second half matters more than it looks: the emulator maps
// its window over everything, so if the iris were still closing when it opened
// the animation would be cut off mid-turn — a hard jump exactly where the whole
// point was to have none. The quickest cold start measured here is over a
// second; this sits comfortably inside that.
const CLOSE_MS = 1500

// Coming back is not the same gesture. The player has just quit and wants the
// library, not a ceremony.
const OPEN_MS = 560

// After the iris shuts, a warm ember fades where it closed. Emulators take one
// to fifteen seconds, so most of the wait is spent on a black screen; without
// this it goes from motion to dead flat in a single frame and reads as a
// freeze. With it the screen settles.
const AFTERGLOW_MS = 1700

// Five arms, turning most of a revolution as they close. A third of a turn —
// where this started — reads as a star shrinking, not as water going down a
// drain: the arms have to travel far enough that the eye follows one round.
const ARMS = 5
const SPIN = Math.PI * 1.55

// Ghost outlines left behind the arms. A single crisp edge is a shape that
// changes size; three fading echoes trailing the rotation is a shape that
// *moves*, and that is the whole difference between a wipe and a vortex.
const TRAILS = 3
const TRAIL_LAG = 0.16   // radians of spin between each echo

const easeIn = (t) => t * t * (3 - 2 * t)          // smooth at both ends
const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v)

/**
 * One frame of the iris, at progress `p` (0 = open, 1 = black).
 *
 * Exported so it can be rendered and looked at on its own — an animation you
 * cannot see a still of is an animation you are guessing about.
 */
export function drawWarp(ctx, w, h, p, accent = '#F0761E', after = 0) {
  ctx.clearRect(0, 0, w, h)
  if (p <= 0) return

  // Shut, and settling: black plus the ember where the iris closed.
  if (p >= 1) {
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, w, h)
    const fade = 1 - Math.min(1, Math.max(0, after))
    if (fade > 0) {
      const g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2,
        Math.min(w, h) * (0.06 + 0.10 * (1 - fade)))
      g.addColorStop(0, accent)
      g.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.save()
      ctx.globalAlpha = 0.34 * fade * fade      // squared: leaves quietly
      ctx.fillStyle = g
      ctx.fillRect(0, 0, w, h)
      ctx.restore()
    }
    return
  }

  const cx = w / 2, cy = h / 2
  // Reach past the corners, so at p=0 not one pixel of the frame is veiled.
  const maxR = Math.hypot(w, h) * 0.62
  const e = easeIn(clamp01(p))
  const R = maxR * (1 - e)
  // The arms deepen as it closes: a gentle ripple at the edge of the screen,
  // a real swirl by the time the hole is small.
  const amp = 0.05 + 0.20 * e
  const spin = e * SPIN

  // The iris outline at a given radius and phase. Modulating the radius by
  // angle is what turns a shutter into a vortex.
  const ring = (radius, phase) => {
    const path = new Path2D()
    const STEPS = 240
    for (let i = 0; i <= STEPS; i++) {
      const a = (i / STEPS) * Math.PI * 2
      const r = radius * (1 + amp * Math.sin(ARMS * a + phase))
      i ? path.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r)
        : path.moveTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r)
    }
    path.closePath()
    return path
  }

  ctx.save()
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, w, h)

  const edge = ring(R, spin)
  ctx.globalCompositeOperation = 'destination-out'
  ctx.fill(edge)

  // Echoes of where the arms just were, drawn inside the hole so they read as
  // motion rather than as extra geometry.
  ctx.globalCompositeOperation = 'source-over'
  ctx.strokeStyle = accent
  ctx.shadowColor = accent
  const visible = Math.min(1, (1 - e) * 2.2)
  for (let t = TRAILS; t >= 1; t--) {
    ctx.globalAlpha = visible * 0.16 * (1 - t / (TRAILS + 1))
    ctx.shadowBlur = 8
    ctx.lineWidth = 1.5
    ctx.stroke(ring(R * (1 - 0.045 * t), spin - TRAIL_LAG * t))
  }

  // The live edge, warm. Without it this is a black shape closing; with it the
  // screen looks lit from the hole, and that is the difference between an
  // effect and a wipe. It fades at the very end, so the last frame is honest
  // black rather than a bright dot left sitting in the middle of the screen.
  ctx.globalAlpha = visible * 0.85
  ctx.shadowBlur = 26 * (1 - e) + 10
  ctx.lineWidth = 2 + 3 * e
  ctx.stroke(edge)
  ctx.restore()
}

export const createWarp = (sdk) => {
  const { html, useRef, useEffect } = sdk.ui

  return () => {
    const ref = useRef(null)
    const playing = sdk.nav.use(s => !!s.sessionGameKey)

    useEffect(() => {
      const canvas = ref.current
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      const accent = getComputedStyle(document.documentElement)
        .getPropertyValue('--accent-mandarin').trim() || '#F0761E'

      let raf = 0, dead = false
      let p = playing ? 1 : 0            // where it is
      const target = playing ? 1 : 0     // where it is going
      let last = 0

      const size = () => {
        const dpr = Math.min(window.devicePixelRatio || 1, 2)
        canvas.width = Math.round(window.innerWidth * dpr)
        canvas.height = Math.round(window.innerHeight * dpr)
      }
      size()

      // Start from the other end so the change is animated, not jumped.
      p = target === 1 ? 0 : 1
      canvas.hidden = false

      let after = 0                      // how far through the ember's fade
      const frame = (now) => {
        if (dead) return
        const dt = last ? now - last : 16
        last = now
        const span = target === 1 ? CLOSE_MS : OPEN_MS
        p += (target - p >= 0 ? 1 : -1) * (dt / span)
        p = clamp01(p)
        if (p >= 1) after = Math.min(1, after + dt / AFTERGLOW_MS)
        drawWarp(ctx, canvas.width, canvas.height, p, accent, after)
        // Done: once the ember has gone the frame is flat black and there is
        // nothing left to draw — the game owns the screen from here. Or, going
        // the other way, take the canvas out of the compositor entirely. Either
        // way the loop ends: a launcher must not keep one spinning behind a
        // running game for the next two hours.
        if (target === 1 && p >= 1 && after >= 1) return
        if (target === 0 && p <= 0) { canvas.hidden = true; return }
        raf = requestAnimationFrame(frame)
      }
      raf = requestAnimationFrame(frame)

      const onResize = () => { size(); drawWarp(ctx, canvas.width, canvas.height, p, accent) }
      window.addEventListener('resize', onResize)
      return () => {
        dead = true
        cancelAnimationFrame(raf)
        window.removeEventListener('resize', onResize)
      }
    }, [playing])

    return html`<canvas class="sm-warp" ref=${ref} data-on=${playing ? '1' : '0'} />`
  }
}
