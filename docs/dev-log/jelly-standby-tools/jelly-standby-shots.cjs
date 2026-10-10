// Dev only: screenshots and a recording of Jelly's standby.
//
//   node jelly-standby-shots.cjs <outdir> [real|stills|none] [--video] [--reduced] [--prefix <p>]
//
// Enters the screensaver stage by answering GET /api/standby with state
// "screensaver" (devserve is read-only; the real timer never runs). `stills`
// keeps the screenshots but drops the clips; `none` empties the playlist.
// The engine marks its phase on `.jl-standby[data-phase]`; the shots wait on it.
const {chromium} = require('/opt/node22/lib/node_modules/playwright')
const args = process.argv.slice(2)
const [OUT, mode = 'real'] = args.filter((a, i) => !a.startsWith('--') && args[i - 1] !== '--prefix')
const BASE = 'http://127.0.0.1:8766'
const video = args.includes('--video')
const reduced = args.includes('--reduced')
const prefix = args.includes('--prefix') ? args[args.indexOf('--prefix') + 1] : 'jelly'
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

async function open(browser, scale = 1) {
  const ctx = await browser.newContext({
    viewport: {width: 1920, height: 1080}, deviceScaleFactor: scale,
    reducedMotion: reduced ? 'reduce' : 'no-preference',
    ...(video ? {recordVideo: {dir: OUT, size: {width: 1920, height: 1080}}} : {}),
  })
  const p = await ctx.newPage()
  await p.route((u) => new URL(u).pathname === '/api/standby', (r) => r.fulfill({
    json: {state: 'screensaver', enabled: true, screensaver_mins: 10, sleep_mins: 20}}))
  if (mode !== 'real') {
    await p.route('**/api/standby/videos*', async (r) => {
      const real = await (await fetch(BASE + '/api/standby/videos')).json()
      r.fulfill({json: mode === 'stills' ? {videos: [], stills: real.stills} : {videos: [], stills: []}})
    })
  }
  await p.goto(BASE + '/')
  await p.waitForSelector('.jl-standby .jl-sb-blob', {timeout: 30000})
  return {ctx, p}
}

const phase = (p, name, timeout = 40000) =>
  p.waitForSelector(`.jl-standby[data-phase="${name}"]`, {timeout}).catch(() => console.log('no phase', name))

;(async () => {
  await fetch(BASE + '/api/themes/active', {method: 'POST', headers: {'content-type': 'application/json'},
    body: JSON.stringify({id: 'jelly'})})
  const browser = await chromium.launch({args: ['--autoplay-policy=no-user-gesture-required']})
  const tag = `${prefix}-${mode}${reduced ? '-reduced' : ''}`
  const {ctx, p} = await open(browser)
  if (video) {
    // Drift and collisions, the first pop (5 s), the first feature (8 s on).
    await wait(21000)
    await ctx.close()
    console.log('video:', await p.video().path())
    await browser.close()
    return
  }
  await wait(3000)
  await p.screenshot({path: `${OUT}/${tag}-swarm.png`})
  // A splat lives 700 ms; poll for it rather than wait on a frame callback.
  const popped = reduced ? '.jl-sb-blob.is-leaving' : '.jl-sb-splat'
  await p.waitForFunction((s) => !!document.querySelector(s), popped, {polling: 30, timeout: 40000})
    .catch(() => console.log('no pop'))
  await wait(reduced ? 300 : 60)
  await p.screenshot({path: `${OUT}/${tag}-pop.png`})
  await phase(p, 'show')
  await wait(2500)
  await p.screenshot({path: `${OUT}/${tag}-feature.png`})
  await wait(5000)
  await p.screenshot({path: `${OUT}/${tag}-feature-2.png`})
  await phase(p, 'release')
  await wait(500)
  await p.screenshot({path: `${OUT}/${tag}-release.png`})
  await ctx.close()
  const zoom = await open(browser, 2)
  await wait(2500)
  for (const [name, sel] of [['caption', '.jl-sb-caption'], ['clock', '.jl-sb-clock']]) {
    const box = await zoom.p.locator(sel).boundingBox()
    if (box) await zoom.p.screenshot({path: `${OUT}/${tag}-${name}.png`,
      clip: {x: box.x - 30, y: box.y - 30, width: box.width + 60, height: box.height + 60}})
  }
  await browser.close()
  console.log('shots:', tag)
})().catch((e) => { console.error(e); process.exit(1) })
