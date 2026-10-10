// Dev only: screenshots and a short recording of the CRT standby.
//
//   node standby-shots.cjs <theme> <outdir> [real|stills|none] [--video] [--reduced]
//
// Enters the screensaver stage by answering GET /api/standby with
// state "screensaver" (the store syncs from it on connect; devserve is
// read-only, so the real trigger cannot run). `stills` keeps the real
// screenshots but drops the clips; `none` empties the playlist.
const {chromium} = require('/opt/node22/lib/node_modules/playwright')
const [theme, OUT, mode = 'real', ...flags] = process.argv.slice(2)
const BASE = 'http://127.0.0.1:8766'
const video = flags.includes('--video')
const reduced = flags.includes('--reduced')
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

async function page(browser, scale = 1) {
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
  await p.waitForSelector('.crt-standby', {timeout: 30000})
  return {ctx, p}
}

;(async () => {
  await fetch(BASE + '/api/themes/active', {method: 'POST', headers: {'content-type': 'application/json'},
    body: JSON.stringify({id: theme})})
  const browser = await chromium.launch({args: ['--autoplay-policy=no-user-gesture-required']})
  const tag = `${theme}-${mode}${reduced ? '-reduced' : ''}`
  const {ctx, p} = await page(browser)
  if (video) {
    await wait(17000)
    await ctx.close()
    console.log('video:', await p.video().path())
    await browser.close()
    return
  }
  await wait(3500)
  await p.screenshot({path: `${OUT}/${tag}-1.png`})
  if (mode !== 'none') {
    // The snow between two channels: catch it as it starts.
    await p.waitForSelector('.crt-tv-static.is-on', {timeout: 30000}).catch(() => {})
    await wait(120)
    await p.screenshot({path: `${OUT}/${tag}-static.png`})
    await wait(3000)
    await p.screenshot({path: `${OUT}/${tag}-2.png`})
  }
  const box = await p.locator('.crt-caption').boundingBox()
  const tv = await p.locator('.crt-tv').boundingBox()
  await ctx.close()
  const zoom = await page(browser, 2)
  await wait(3500)
  if (box) await zoom.p.screenshot({path: `${OUT}/${tag}-caption.png`,
    clip: {x: box.x - 24, y: box.y - 24, width: box.width + 48, height: box.height + 48}})
  if (tv) await zoom.p.screenshot({path: `${OUT}/${tag}-tv.png`,
    clip: {x: tv.x - 120, y: tv.y - 90, width: tv.width + 240, height: tv.height + 260}})
  await browser.close()
  console.log('shots:', tag)
})().catch((e) => { console.error(e); process.exit(1) })
