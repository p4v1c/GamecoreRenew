// Dev only: the PC library through the real backend (docs/dev-log/pc-pack.md).
// devserve must run with HOME pointing at a fake Lutris home, so the lutris
// pack's sync writes real stubs and covers (fixture: pc-fixture.py).
//   node pc-library-shots.cjs <outdir> <theme|default> <name:key,key> ...
const {chromium} = require('/opt/node22/lib/node_modules/playwright')
const fs = require('fs')
const [OUT, theme, ...steps] = process.argv.slice(2)
const gp = (p, k) => p.evaluate((k) => window.dispatchEvent(new CustomEvent('gp:' + k)), k)
;(async () => {
  await fetch('http://127.0.0.1:8766/api/themes/active', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({id: theme === 'default' ? null : theme})})
  const b = await chromium.launch()
  const p = await b.newPage({viewport: {width: 1920, height: 1080}})
  await p.addInitScript(fs.readFileSync('/home/user/GamecoreRenew/.claude/skills/gamecore-legibility/scripts/fake-pads.js', 'utf8'))
  await p.goto('http://127.0.0.1:8766/?pads=xbox')
  await p.waitForTimeout(7000); await gp(p, 'back'); await p.waitForTimeout(2500)
  for (const s of steps) {
    const [name, keys] = s.split(':')
    for (const k of (keys ? keys.split(',') : [])) { await gp(p, k); await p.waitForTimeout(900) }
    await p.waitForTimeout(2500)
    await p.screenshot({path: `${OUT}/${theme}-${name}.png`})
  }
  await b.close()
})()
