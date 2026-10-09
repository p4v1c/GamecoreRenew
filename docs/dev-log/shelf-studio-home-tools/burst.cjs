// Library burst: open a console's shelf, press d-pad right N times every I ms,
// record CDP screencast frames and a per-frame sample of the jacket's 3D state.
//   node burst.cjs <outdir> <system> <intervalMs> <presses> [left]
const fs = require('fs')
const {open, wait, focusHome, gp} = require('./lib.cjs')
;(async () => {
  const [out, sys, interval, presses, dirArg] = process.argv.slice(2)
  const dir = dirArg === 'left' ? 'dpad-left' : 'dpad-right'
  fs.rmSync(out, {recursive: true, force: true}); fs.mkdirSync(out, {recursive: true})
  const {b, p} = await open()
  await focusHome(p, sys)
  await gp(p, 'confirm'); await wait(p, 3500)
  if (dir === 'dpad-left') { for (let i = 0; i < +presses; i++) { await gp(p, 'dpad-right'); await wait(p, 60) } await wait(p, 2500) }
  // Per-frame sampler: every holder, its phase and key, and the angle the solid
  // is actually turned to (from its computed matrix), plus the carry's travel.
  await p.evaluate(() => {
    window.__samples = []
    const angle = (el) => {
      if (!el) return null
      const m = getComputedStyle(el).transform
      if (!m || m === 'none') return 0
      const v = m.match(/matrix3d\((.+)\)/)
      if (!v) return 0
      const a = v[1].split(',').map(Number)
      // rotateY component: atan2(-m13, m11) on the upper 3x3 (column-major)
      return Math.round(Math.atan2(a[8], a[0]) * 180 / Math.PI)
    }
    const tz = (el) => {
      if (!el) return null
      const m = getComputedStyle(el).transform
      const v = m && m.match(/matrix3d\((.+)\)/)
      return v ? v[1].split(',').map(Number).slice(12, 15).map(Math.round) : [0, 0, 0]
    }
    const t0 = performance.now()
    const tick = () => {
      const holds = [...document.querySelectorAll('.cz-hold')].map((h) => ({
        phase: h.dataset.phase, tucked: h.dataset.tucked, vis: getComputedStyle(h).visibility,
        op: getComputedStyle(h).opacity,
        turn: angle(h.querySelector('.cz-box')), move: tz(h.querySelector('.cz-carry')),
        key: h.dataset.game || (h.querySelector('.cz-f-front img') || {}).alt || null,
        imgs: [...h.querySelectorAll('.cz-f img')].map((i) => i.complete && i.naturalWidth > 0 ? 1 : 0).join(''),
      }))
      const gaps = document.querySelectorAll('.cz-slot[data-gap="1"]').length
      window.__samples.push({t: Math.round(performance.now() - t0), holds, gaps})
      if (window.__sampling) requestAnimationFrame(tick)
    }
    window.__sampling = true
    requestAnimationFrame(tick)
  })
  const cdp = await p.context().newCDPSession(p)
  const frames = []
  cdp.on('Page.screencastFrame', async (f) => {
    frames.push({t: f.metadata.timestamp, data: f.data})
    try { await cdp.send('Page.screencastFrameAck', {sessionId: f.sessionId}) } catch {}
  })
  await cdp.send('Page.startScreencast', {format: 'jpeg', quality: 85, everyNthFrame: 1})
  await wait(p, 300)
  const pressAt = []
  for (let i = 0; i < +presses; i++) {
    pressAt.push(Date.now() / 1000)
    await gp(p, dir)
    await wait(p, +interval)
  }
  await wait(p, 1800)
  await cdp.send('Page.stopScreencast')
  const samples = await p.evaluate(() => { window.__sampling = false; return window.__samples })
  frames.forEach((f, i) => fs.writeFileSync(`${out}/f${String(i).padStart(4, '0')}.jpg`, Buffer.from(f.data, 'base64')))
  fs.writeFileSync(`${out}/frames.json`, JSON.stringify({frames: frames.map((f) => f.t), pressAt}))
  fs.writeFileSync(`${out}/samples.json`, JSON.stringify(samples))
  console.log('frames', frames.length, 'samples', samples.length)
  await b.close()
})()
