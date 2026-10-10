// Dev only: screenshots of the PC case with a fake `lutris` system (docs/dev-log/pc-pack.md).
//   node pc-shots.cjs <outdir> <theme> <name:key,key[:x,y,w,h as XxYxWxH]> ...   (DPR=2 for close-ups)
// Real-code check: /api/media/lutris/* answered from pcmock (what a PC source will return).
const {chromium} = require('/opt/node22/lib/node_modules/playwright')
const fs = require('fs'), path = require('path')
const S = __dirname, M = path.join(S, 'pcmock'), data = JSON.parse(fs.readFileSync(path.join(M, 'data.json')))
const [OUT, theme, ...steps] = process.argv.slice(2)
const gp = (p, k) => p.evaluate((k) => window.dispatchEvent(new CustomEvent('gp:' + k)), k)
const REQ = {OS: 'os', Processor: 'cpu', Memory: 'ram', Graphics: 'gpu', Storage: 'disk'}
const tidy = (v) => String(v || '').replace(/ available space| of available space|\(.*?\)/gi, '').replace(/ or (better|newer|later|above|greater)/i, '+').trim()
;(async () => {
  await fetch('http://127.0.0.1:8766/api/themes/active', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({id: theme})})
  const b = await chromium.launch()
  const p = await b.newPage({viewport: {width: 1920, height: 1080}, deviceScaleFactor: Number(process.env.DPR || 1)})
  await p.addInitScript(fs.readFileSync('/home/user/GamecoreRenew/.claude/skills/gamecore-legibility/scripts/fake-pads.js', 'utf8'))
  await p.route(/\/api\/media\/lutris\//, (r) => {
    const u = decodeURIComponent(new URL(r.request().url()).pathname)
    const m = /\/api\/media\/lutris\/(.+?)\.lutris(?:\/media\/(.+))?$/.exec(u)
    const g = m && data[m[1]]
    if (!g) return r.fulfill({status: 404, json: {}})
    const files = {'clear-logo': g.logo, 'screenshot-gameplay': g.shots[2], 'screenshot-game-title': g.shots[3], 'fanart-background': g.shots[1]}
    if (m[2]) return files[m[2]] ? r.fulfill({path: path.join(S, files[m[2]])}) : r.fulfill({status: 404, json: {}})
    const req = Object.fromEntries(Object.entries(g.reqs).filter(([k]) => REQ[k]).map(([k, v]) => [REQ[k], tidy(v)]))
    r.fulfill({json: {found: true, available: true, media: Object.fromEntries(Object.keys(files).filter((k) => files[k]).map((k) => [k, {kind: 'image'}])),
      meta: {title: m[1], description: g.blurb, developer: g.developer, publisher: g.publisher, year: g.year, genres: g.genres, players_label: '1', requirements: req}}})
  })
  await p.goto('http://127.0.0.1:8766/?pads=xbox')
  await p.waitForTimeout(7000); await gp(p, 'back'); await p.waitForTimeout(2500)
  for (const s of steps) {
    const [name, keys, clip] = s.split(':')
    for (const k of (keys ? keys.split(',') : [])) { await gp(p, k); await p.waitForTimeout(800) }
    await p.waitForTimeout(2500)
    const c = clip ? clip.split('x').map(Number) : null
    await p.screenshot({path: `${OUT}/${theme}-${name}.png`, ...(c ? {clip: {x: c[0], y: c[1], width: c[2], height: c[3]}} : {})})
  }
  await b.close()
})()
