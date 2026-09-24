/** Settings backdrop: a watch movement turning behind the category list.
 *
 * Ported from the "Orbit Settings Calibre" mockup. The gears really mesh —
 * each one is placed at pitch distance from the one it drives, phased so the
 * teeth interlock, and turns the other way at the inverse ratio — so the
 * animation reads as one mechanism rather than wheels spinning at random.
 *
 * Built once as an SVG string and animated with SMIL: no script runs per
 * frame, and the markup is the same on every visit.
 */
const TAU = Math.PI * 2
const f = (n) => (+n).toFixed(2)

const circ = (r) => `M${f(r)},0A${f(r)},${f(r)} 0 1,0 ${f(-r)},0A${f(r)},${f(r)} 0 1,0 ${f(r)},0Z`

function teeth(n, m) {
  const rp = m * n / 2, ro = rp + m, rr = rp - 1.25 * m, a = TAU / n, p = []
  for (let i = 0; i < n; i++) {
    const t = i * a - 0.275 * a
    for (const [g, r] of [[t, rr], [t + 0.13 * a, ro], [t + 0.42 * a, ro], [t + 0.55 * a, rr]])
      p.push(f(Math.cos(g) * r) + ',' + f(Math.sin(g) * r))
  }
  return 'M' + p.join('L') + 'Z'
}

// Each gear after the first is positioned against the one it meshes with.
function mesh(m, list) {
  const out = []
  for (const g of list) {
    let x, y, phase, dir
    if (g.from == null) { x = g.x; y = g.y; phase = g.phase || 0; dir = 1 }
    else {
      const p = out[g.from], d = (p.n + g.n) * m / 2, phi = g.ang * Math.PI / 180, ratio = p.n / g.n
      x = p.x + Math.cos(phi) * d; y = p.y + Math.sin(phi) * d
      phase = (-ratio * p.phase * Math.PI / 180 + phi * (1 + ratio) + Math.PI / g.n) * 180 / Math.PI
      dir = -p.dir
    }
    out.push({...g, m, x, y, phase, dir})
  }
  return out
}

const CLUSTERS = [
  {m: 12, gears: [{x: 300, y: 330, n: 20, kind: 'spokes', spokes: 5}, {from: 0, ang: 152, n: 12, kind: 'rings'}, {from: 0, ang: 28, n: 10, kind: 'spokes', spokes: 3}, {from: 2, ang: 92, n: 14, kind: 'spokes', spokes: 3}, {from: 0, ang: -58, n: 22, kind: 'spokes', spokes: 6}, {from: 3, ang: 170, n: 8, kind: 'solid'}]},
  {m: 9, gears: [{x: 150, y: 860, n: 16, kind: 'spokes', spokes: 4}, {from: 0, ang: 8, n: 10, kind: 'rings'}, {from: 0, ang: -118, n: 8, kind: 'solid'}]},
  {m: 6, far: true, gears: [{x: 70, y: 600, n: 12, kind: 'solid'}, {from: 0, ang: 60, n: 8, kind: 'solid'}]},
  {m: 12, gears: [{x: 1590, y: 520, n: 14, kind: 'spokes', spokes: 3}, {from: 0, ang: 38, n: 10, kind: 'rings'}, {from: 1, ang: 62, n: 20, kind: 'spokes', spokes: 5}, {from: 0, ang: 128, n: 8, kind: 'solid'}, {from: 2, ang: -20, n: 12, kind: 'spokes', spokes: 4}]},
  {m: 12, gears: [{x: 1500, y: 1040, n: 22, kind: 'spokes', spokes: 6, phase: 5}]},
  {m: 6, far: true, gears: [{x: 1720, y: 330, n: 12, kind: 'rings'}, {from: 0, ang: 200, n: 9, kind: 'solid'}]},
]

const HEX = [[60, 120, 24, [[0, 0], [1, 0], [0, 1], [-1, 1], [1, -1], [2, -1]]], [520, 380, 22, [[0, 0], [1, 0], [2, 0], [3, -1], [4, -1], [-1, 1]]], [60, 590, 26, [[0, 0], [1, 0], [2, 0], [1, 1], [2, 1], [3, 0], [4, -1]]], [1330, 580, 22, [[0, 0], [1, 0], [2, 0], [3, 0], [4, -1], [5, -1]]], [1760, 380, 24, [[0, 0], [1, 0], [2, 0], [0, 1], [1, 1], [3, -1], [-1, 1]]], [1600, 140, 20, [[0, 0], [1, 0], [0, 1], [2, -1]]], [1840, 870, 22, [[0, 0], [1, 0], [0, 1], [-1, 1]]]]

function hexPath(r) {
  let p = ''
  for (let i = 0; i < 6; i++) {
    const a = Math.PI / 6 + i * TAU / 6
    p += (i ? 'L' : 'M') + f(Math.cos(a) * r) + ',' + f(Math.sin(a) * r)
  }
  return p + 'Z'
}

function hexes() {
  return HEX.map(([cx, cy, r, cells]) => `<g transform="translate(${cx} ${cy})">${cells.map(([q, s]) =>
    `<path d="${hexPath(r * 0.92)}" transform="translate(${f(Math.sqrt(3) * r * (q + s / 2))} ${f(1.5 * r * s)})" fill="none" stroke="#5f7090" stroke-opacity=".45" stroke-width="1.2"/>`
  ).join('')}</g>`).join('')
}

const P = {face: '#1c2639', spoke: '#253150', hub: '#2f3c5a', edge: '#b3c3dc', eo: 0.6}

function wheel(g, k) {
  const {n, m} = g, rp = m * n / 2, rr = rp - 1.25 * m, rim = rr - 1.6 * m, hub = Math.max(rp * 0.16, m * 1.8)
  let kids
  if (g.kind === 'solid') {
    kids = `<path d="${teeth(n, m)}${circ(rr * 0.42)}" fill-rule="evenodd" fill="${P.face}" stroke="${P.edge}" stroke-opacity="${P.eo}" stroke-width="1.1"/>`
      + `<circle r="${f(rr * 0.7)}" fill="none" stroke="${P.edge}" stroke-opacity=".35" stroke-width="${f(m * 0.45)}" stroke-dasharray="${f(m * 1.2)} ${f(m * 0.8)}"/>`
  } else {
    kids = `<path d="${teeth(n, m)}${circ(rim)}" fill-rule="evenodd" fill="${P.face}" stroke="${P.edge}" stroke-opacity="${P.eo}" stroke-width="1.1"/>`
    if (g.kind === 'rings') {
      kids += `<circle r="${f(rim * 0.68)}" fill="none" stroke="${P.spoke}" stroke-width="${f(rim * 0.2)}" stroke-dasharray="${f(rim * 0.9)} ${f(rim * 0.28)}"/>`
        + `<circle r="${f(rim * 0.28)}" fill="${P.spoke}" stroke="${P.edge}" stroke-opacity="${P.eo}"/>`
    } else {
      const w = Math.max(m * 1.2, rp * 0.09)
      for (let j = 0; j < g.spokes; j++)
        kids += `<rect x="0" y="${f(-w / 2)}" width="${f(rim + 1)}" height="${f(w)}" fill="${P.spoke}" transform="rotate(${j * 360 / g.spokes})"/>`
      kids += `<path d="${circ(hub)}${circ(hub * 0.38)}" fill-rule="evenodd" fill="${P.hub}" stroke="${P.edge}" stroke-opacity="${P.eo}"/>`
    }
  }
  // Speed follows tooth count, so meshed gears turn at the right ratio.
  const spin = `<animateTransform attributeName="transform" type="rotate" from="0" to="${360 * g.dir}" dur="${f(n * k)}s" repeatCount="indefinite"/>`
  return `<g transform="translate(${f(g.x)} ${f(g.y)}) rotate(${f(g.phase)})"><g>${kids}${spin}</g></g>`
}

const jewel = (x, y, r) => `<g><circle cx="${f(x)}" cy="${f(y)}" r="${r + 5}" fill="#2a3550" stroke="#c7d4e8" stroke-opacity=".55" stroke-width="1"/>`
  + `<circle cx="${f(x)}" cy="${f(y)}" r="${r}" fill="url(#orbit-ruby)"/>`
  + `<circle cx="${f(x - r * 0.3)}" cy="${f(y - r * 0.35)}" r="${f(r * 0.28)}" fill="#fff" fill-opacity=".55"/></g>`

/** The whole movement as one SVG string. `speed` 1 is the mockup's pace. */
export function gearsSvg(speed = 1) {
  const k = 1.5 / speed, bal = {x: 1380, y: 190}, BR = 92
  const chains = CLUSTERS.map(c => ({...c, g: mesh(c.m, c.gears)}))

  let screws = ''
  for (let j = 0; j < 10; j++) {
    const a = j * TAU / 10
    screws += `<circle cx="${f(Math.cos(a) * (BR + 5))}" cy="${f(Math.sin(a) * (BR + 5))}" r="4.5" fill="url(#orbit-blued)" stroke="#0a0e16"/>`
  }
  let spring = ''
  for (let t = 0; t <= 1; t += 0.004) {
    const a = t * 7 * TAU, r = 12 + t * 38
    spring += (t ? 'L' : 'M') + f(bal.x + Math.cos(a) * r) + ',' + f(bal.y + Math.sin(a) * r)
  }
  const balance = `<g transform="translate(${bal.x} ${bal.y})"><g>`
    + `<circle r="${BR}" fill="none" stroke="#0a0e16" stroke-width="16"/><circle r="${BR}" fill="none" stroke="#8d9fbc" stroke-width="11"/>`
    + `<circle r="${BR}" fill="none" stroke="#e3ecf8" stroke-opacity=".35" stroke-width="2" transform="translate(-1 -2)"/>`
    + [0, 120, 240].map(a => `<rect x="0" y="-3.5" width="${BR}" height="7" fill="#8d9fbc" stroke="#0a0e16" transform="rotate(${a})"/>`).join('')
    + screws
    + `<animateTransform attributeName="transform" type="rotate" values="-170;170;-170" keyTimes="0;.5;1" calcMode="spline" keySplines=".45 0 .55 1;.45 0 .55 1" dur="${f(1.4 / speed)}s" repeatCount="indefinite"/>`
    + `</g></g>`

  const wheels = chains.flatMap(c => c.g.map(g => c.far ? `<g opacity=".55">${wheel(g, k)}</g>` : wheel(g, k))).join('')
  const jewels = chains.flatMap(c => c.g.filter(g => g.kind !== 'solid').map(g => jewel(g.x, g.y, Math.max(4, g.m * 0.7)))).join('')

  return `<svg viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice" style="display:block;width:100%;height:100%;stroke:none;stroke-width:1;stroke-linecap:butt;stroke-linejoin:miter">`
    + `<defs>`
    + `<radialGradient id="orbit-ruby" cx=".4" cy=".35"><stop offset="0" stop-color="#ff7a8a"/><stop offset=".6" stop-color="#b0213a"/><stop offset="1" stop-color="#5a0b1c"/></radialGradient>`
    + `<radialGradient id="orbit-blued" cx=".35" cy=".3"><stop offset="0" stop-color="#6d9bff"/><stop offset=".55" stop-color="#2448b8"/><stop offset="1" stop-color="#10205e"/></radialGradient>`
    + `<radialGradient id="orbit-wash" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#080b11" stop-opacity=".92"/><stop offset=".6" stop-color="#080b11" stop-opacity=".6"/><stop offset="1" stop-color="#080b11" stop-opacity="0"/></radialGradient>`
    + `</defs>`
    + `<rect width="1920" height="1080" fill="#0d121c"/>`
    + `<g opacity=".6">${hexes()}</g>`
    + `<path d="${spring}" fill="none" stroke="#9fb3d2" stroke-opacity=".55" stroke-width=".8"/>${balance}`
    + wheels + jewels + jewel(bal.x, bal.y, 6)
    + `<ellipse cx="960" cy="540" rx="600" ry="760" fill="url(#orbit-wash)"/>`
    + `</svg>`
}

// Never changes, so it is built on first use and kept.
let cached = null
export const settingsGears = () => (cached ??= gearsSvg(1))
