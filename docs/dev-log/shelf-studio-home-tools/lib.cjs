// Shared helpers for Shelf screenshots against the read-only dev server on :8766.
const {chromium} = require('/opt/node22/lib/node_modules/playwright')
const fs = require('fs')
const BASE = 'http://127.0.0.1:8766'
const PADS = '/home/user/GamecoreRenew/.claude/skills/gamecore-legibility/scripts/fake-pads.js'
const gp = (p, k) => p.evaluate((k) => window.dispatchEvent(new CustomEvent('gp:' + k)), k)
const wait = (p, ms) => p.waitForTimeout(ms)
async function open(opts = {}) {
  opts = {...opts, ...(process.env.SLOW_COVERS ? {slowCovers: +process.env.SLOW_COVERS} : {})}
  await fetch(BASE + '/api/themes/active', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({id: 'shelf'})})
  const b = await chromium.launch()
  const ctx = await b.newContext({viewport: {width: 1920, height: 1080}, ...(opts.video ? {recordVideo: {dir: opts.video, size: {width: 1920, height: 1080}}} : {})})
  const p = await ctx.newPage()
  p.on('pageerror', (e) => console.log('PAGEERROR', e.message))
  p.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.log('CONSOLE', m.type(), m.text().slice(0, 300)) })
  if (opts.session) {
    // The socket announces the session on connect ({event: 'game:running'}),
    // which would overwrite a faked HTTP answer, so both are rewritten.
    await p.route('**/api/games/session', (r) => r.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(opts.session)}))
    await p.routeWebSocket(/\/ws$/, (ws) => {
      const server = ws.connectToServer()
      server.onMessage((m) => {
        try { const j = JSON.parse(m); if (j.event === 'game:running') { ws.send(JSON.stringify({event: 'game:running', data: opts.session})); return } } catch {}
        ws.send(m)
      })
    })
  }
  if (opts.slowCovers) {
    // A slow box: every jacket takes this long to arrive, as an uncached cover does there.
    await p.route('**/api/covers/**', async (r) => { await new Promise((ok) => setTimeout(ok, opts.slowCovers)); r.continue() })
  }
  await p.addInitScript(fs.readFileSync(PADS, 'utf8'))
  await p.goto(BASE + '/?pads=xbox')
  await p.waitForSelector('.gcs-who', {timeout: 30000}).catch(() => {})
  await wait(p, 1500); await gp(p, 'back'); await wait(p, 2500)
  return {b, ctx, p}
}
/** Move the home cursor onto the system with this id (presses right from the start). */
async function focusHome(p, id) {
  const ids = await p.evaluate(() => fetch('/api/systems').then(r => r.json()).then(l => l.map(s => s.id)))
  const target = ids.indexOf(id)
  const now = await p.evaluate(() => window.__gcStore ? 0 : 0)
  for (let i = 0; i < 60; i++) { await gp(p, 'dpad-left') }
  await wait(p, 300)
  for (let i = 0; i < target; i++) { await gp(p, 'dpad-right'); await wait(p, 40) }
  await wait(p, 1400)
}
module.exports = {open, gp, wait, focusHome, BASE}
