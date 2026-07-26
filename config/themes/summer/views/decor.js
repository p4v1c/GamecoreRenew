/**
 * The dune foreground: marram grass and shells.
 *
 * Blades are generated exactly as the mockup did — a seeded PRNG, so the dune
 * is identical on every boot — and swayed in CSS, never in JS. Shells are the
 * mockup's seven hand-placed positions. No surfer: the brief's narrative
 * element was dropped on request.
 */
import { todColors, shade } from '../lib/ocean.js'

const makeBlades = (seed, count, spread) => {
  let s = seed
  const rnd = () => { s = (s * 16807) % 2147483647; return s / 2147483647 }
  const out = []
  for (let i = 0; i < count; i++) {
    const back = i % 3 === 0
    const u = i / count
    const x = -40 + Math.pow(u, 1.8) * spread + rnd() * 22
    const near = 1.35 - 0.65 * u
    const h = ((back ? 80 : 130) + rnd() * (back ? 80 : 160)) * near
    const lean = (rnd() - 0.5) * (h * 0.42)
    const w = ((back ? 4 : 5.5) + rnd() * 4) * near
    const cx = x + lean * 0.28, cy = 300 - h * 0.52
    const d = `M${(x - w).toFixed(1)} 300 Q${(cx - w * 0.35).toFixed(1)} ${cy.toFixed(1)} `
            + `${(x + lean).toFixed(1)} ${(300 - h).toFixed(1)} `
            + `Q${(cx + w * 0.4).toFixed(1)} ${(cy + 4).toFixed(1)} ${(x + w).toFixed(1)} 300 Z`
    out.push({
      d, depth: back ? 0.5 + rnd() * 0.16 : 0.78 + rnd() * 0.42,
      kf: `smB${h > 230 ? 3 : h > 150 ? 2 : 1}`,
      dur: (1.7 + rnd() * 1.5).toFixed(2),
      delay: (-(x / spread) * 1.6 - rnd() * 0.5).toFixed(2),
    })
  }
  return out.sort((a, b) => a.depth - b.depth)
}

// left, top, size, rotation — the mockup's placement, kept
const SHELLS = [
  [13, 86, 34, -14], [27, 81, 24, 9], [41, 94, 40, -6], [52, 84, 26, 22],
  [63, 90, 32, -19], [76, 82, 22, 6], [88, 92, 36, 15],
]

export const createDecor = (sdk, useIdle) => {
  const { html, useState, useEffect, useMemo } = sdk.ui
  return () => {
    const idle = useIdle()
    // The dune belongs to the beach view. Over the library it just sits on top
    // of the cover art, so it stays on the dashboard.
    const screen = sdk.nav.use(s => s.screen)
    const left = useMemo(() => makeBlades(12345, 38, 760), [])
    const right = useMemo(() => makeBlades(987654, 34, 720), [])
    const [c, setC] = useState(() => todColors())
    useEffect(() => {
      const t = setInterval(() => setC(todColors()), 60000)
      return () => clearInterval(t)
    }, [])
    if (idle || screen !== 'home') return null

    const blade = (b, i, tint) => html`
      <path key=${i} d=${b.d} fill=${shade(c.grass, b.depth * tint)}
        style=${{
          transformBox: 'fill-box', transformOrigin: '50% 100%',
          animation: `${b.kf} ${b.dur}s cubic-bezier(.36,.07,.19,.97) ${b.delay}s infinite`,
        }} />`

    return html`
      <div class="sm-decor">
        ${SHELLS.map((v, i) => html`
          <svg key=${i} class="sm-shell" viewBox="0 0 40 32"
               style=${{ left: `${v[0]}%`, top: `${v[1]}%`, width: `${v[2]}px`,
                         transform: `rotate(${v[3]}deg)` }}>
            <path d="M20 31 C6 31 1 21 2 13 C3 6 10 1 20 1 C30 1 37 6 38 13 C39 21 34 31 20 31 Z"
                  fill=${shade(c.sandNear, 1.08)} stroke=${shade(c.sandWet, 0.88)} stroke-width="1.2" />
            <path d="M20 31 L20 2 M20 31 L9 6 M20 31 L31 6 M20 31 L4 14 M20 31 L36 14"
                  stroke=${shade(c.sandWet, 0.92)} stroke-width="1" fill="none" opacity="0.75" />
          </svg>`)}
        <svg class="sm-grass sm-grass-l" viewBox="0 0 760 300" preserveAspectRatio="none">
          ${left.map((b, i) => blade(b, i, 1))}
        </svg>
        <svg class="sm-grass sm-grass-r" viewBox="0 0 720 300" preserveAspectRatio="none">
          ${right.map((b, i) => blade(b, i, 0.96))}
        </svg>
      </div>`
  }
}
