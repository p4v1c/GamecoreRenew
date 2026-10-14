// Dev only: the "Wait for the TV after waking" setting in every theme, and the
// black layer through a sleep.
//
//   node wake-shots.cjs <outdir> [theme ...]
//
// devserve.py on :8766 (read-only). Pads from the legibility skill's
// fake-pads.js: 9 opens Settings, 12/13 d-pad up/down, 15 right, 0 is ✕.
// `__sleep()` / `__wake()` feed the page `power:sleeping` / `power:resumed`
// through its own socket handler, as the backend does around a real sleep.
const {chromium} = require('/opt/node22/lib/node_modules/playwright')
const fs = require('fs')
const path = require('path')
const BASE = 'http://127.0.0.1:8766'
const FAKE = fs.readFileSync(path.join(__dirname, '../../../.claude/skills/gamecore-legibility/scripts/fake-pads.js'), 'utf8')
const WS = `(() => {
  const Real = window.WebSocket
  window.WebSocket = class extends Real {
    set onmessage(fn) { window.__wsHandler = fn; super.onmessage = fn }
    get onmessage() { return window.__wsHandler }
  }
  let n = 0
  const send = (event, data) => window.__wsHandler?.({data: JSON.stringify({event, data})})
  window.__sleep = () => send('power:sleeping', {})
  window.__wake = () => send('power:resumed', {resumes: ++n})
})()`
const [OUT, ...wanted] = process.argv.slice(2)
const THEMES = wanted.length ? wanted : ['default', 'shelf', 'orbit', 'jelly', 'summer']
const ROW = '.gcs-row2[aria-label="Wait for the TV after waking"]'
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

;(async () => {
  fs.mkdirSync(OUT, {recursive: true})
  const browser = await chromium.launch()
  for (const id of THEMES) {
    await fetch(BASE + '/api/themes/active', {method: 'POST', headers: {'content-type': 'application/json'},
      body: JSON.stringify({id: id === 'default' ? null : id})})
    const ctx = await browser.newContext({viewport: {width: 1920, height: 1080}})
    const p = await ctx.newPage()
    await p.addInitScript(WS)
    await p.addInitScript(FAKE)
    await p.goto(`${BASE}/?pads=ds4`)
    await wait(9000)
    const press = async (b, after = 450) => { await p.evaluate((x) => window.__press(x), b); await wait(after) }
    await press(1, 400)
    await press(9, 1500)                                  // Settings
    // Down the category list until the System page is drawn; themes differ in
    // whether the page follows the cursor or needs ✕, so both are tried. A
    // press can be swallowed while a page animates, so a click on the rail's
    // "System" is the fallback (the shot is of the row, not of the walk).
    for (let i = 0; i < 12 && !(await p.$(ROW)); i++) await press(13, 600)
    let clicked = false
    if (!(await p.$(ROW))) {
      await p.getByText('System', {exact: true}).last().click().catch(() => {})
      await wait(1200)
      clicked = true
    }
    // ✕ on the page's first row would check for updates; after a click, click.
    for (let i = 0; !clicked && i < 3 && !(await p.$(`${ROW}[data-on="1"]`)); i++) {
      await press(0, 900)                                 // into the page
      for (let j = 0; j < 8 && !(await p.$(`${ROW}[data-on="1"]`)); j++) await press(13, 500)
    }
    if (!(await p.$(`${ROW}[data-on="1"]`))) await p.click(ROW).catch(() => {})
    if (!(await p.$(`${ROW}[data-on="1"]`))) console.log('row not focused:', id)
    await wait(600)
    await p.screenshot({path: `${OUT}/wake-setting-${id}.png`})
    for (let i = 0; i < 3; i++) await press(1, 900)
    await p.evaluate(() => window.__sleep())
    await wait(500)
    await p.screenshot({path: `${OUT}/wake-black-${id}.png`})
    await p.evaluate(() => window.__wake())
    await wait(250)
    await p.screenshot({path: `${OUT}/wake-splash-start-${id}.png`})
    await ctx.close()
    console.log('shots:', id)
  }
  await browser.close()
})()
