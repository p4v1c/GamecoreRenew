// Dev only: the power menu in every theme, and the wake replay.
//
//   node power-shots.cjs <outdir> [theme ...]
//
// Needs devserve.py on :8766 (read-only). POST /api/power/rest is answered
// with the backend's refusal, for the "refused" shot. Pads come from the legibility
// skill's fake-pads.js; button 8 opens the power menu, 0 is ✕, 12/13 d-pad.
// `__wake()` feeds the page the `power:resumed` event the backend sends after
// a real wake, through the page's own socket handler.
const {chromium} = require('/opt/node22/lib/node_modules/playwright')
const fs = require('fs')
const path = require('path')
const BASE = 'http://127.0.0.1:8766'
const FAKE = fs.readFileSync(path.join(__dirname, '../../../.claude/skills/gamecore-legibility/scripts/fake-pads.js'), 'utf8')
const WAKE = `(() => {
  const Real = window.WebSocket
  window.WebSocket = class extends Real {
    set onmessage(fn) { window.__wsHandler = fn; super.onmessage = fn }
    get onmessage() { return window.__wsHandler }
  }
  let n = 0
  window.__wake = () => window.__wsHandler?.({data: JSON.stringify({event: 'power:resumed', data: {resumes: ++n}})})
})()`
const [OUT, ...wanted] = process.argv.slice(2)
const THEMES = wanted.length ? wanted : ['default', 'shelf', 'orbit', 'jelly', 'summer']
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

async function theme(id) {
  await fetch(BASE + '/api/themes/active', {method: 'POST', headers: {'content-type': 'application/json'},
    body: JSON.stringify({id: id === 'default' ? null : id})})
}

async function page(browser, query) {
  const ctx = await browser.newContext({viewport: {width: 1920, height: 1080}})
  const p = await ctx.newPage()
  await p.addInitScript(WAKE)
  await p.addInitScript(FAKE)
  // What the real backend answers on a box without the sudoers rule.
  await p.route('**/api/power/rest', (r) => r.fulfill({status: 503,
    json: {detail: "Couldn’t sleep. Update GameCore, then try again."}}))
  await p.goto(`${BASE}/?pads=ds4${query}`)
  await wait(9000)                     // boot animation, then Home
  const press = async (b, after = 700) => { await p.evaluate((x) => window.__press(x), b); await wait(after) }
  await press(1, 400)                  // the first press only wakes the box
  return {ctx, p, press}
}

;(async () => {
  fs.mkdirSync(OUT, {recursive: true})
  const browser = await chromium.launch()
  for (const id of THEMES) {
    await theme(id)
    let {ctx, p, press} = await page(browser, '')
    await press(8, 1200)
    await p.screenshot({path: `${OUT}/${id}-power.png`})
    await press(0)
    await p.screenshot({path: `${OUT}/${id}-power-confirm.png`})
    await press(0, 1500)               // refused (stubbed 503): the reason shows
    await p.screenshot({path: `${OUT}/${id}-power-refused.png`})
    await press(13); await press(13); await press(13)
    await p.screenshot({path: `${OUT}/${id}-power-desktop.png`})
    await press(1, 900)                // ○ closes
    await p.evaluate(() => window.__wake())
    await wait(700)
    await p.screenshot({path: `${OUT}/${id}-wake-splash.png`})
    await wait(9000)
    await p.screenshot({path: `${OUT}/${id}-wake-home.png`})
    await ctx.close();
    ({ctx, p, press} = await page(browser, '&bg=1'))
    await press(8, 1200)
    await p.screenshot({path: `${OUT}/${id}-power-bg.png`})
    await ctx.close()
    console.log('shots:', id)
  }
  await browser.close()
})()
