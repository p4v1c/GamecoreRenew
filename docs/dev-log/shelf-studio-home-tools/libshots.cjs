const {open, wait, focusHome, gp} = require('./lib.cjs')
;(async () => {
  const out = process.argv[2]
  const {b, p} = await open()
  await p.evaluate(() => { try { localStorage.setItem('gc:shelf:libraryMode', 'shelf') } catch {} })
  await focusHome(p, 'azahar'); await gp(p, 'confirm'); await wait(p, 3500)
  await p.screenshot({path: `${out}/lib-3ds.png`})
  await gp(p, 'l2'); await wait(p, 900); await p.screenshot({path: `${out}/lib-3ds-flipped.png`})
  await gp(p, 'dpad-right'); await wait(p, 180); await p.screenshot({path: `${out}/lib-3ds-swap-mid.png`})
  await wait(p, 1500); await p.screenshot({path: `${out}/lib-3ds-next.png`})
  for (const m of ['stack', 'gallery']) {
    await gp(p, 'r2'); await wait(p, 1500); await p.screenshot({path: `${out}/lib-3ds-${m}.png`})
    await gp(p, 'dpad-left'); await wait(p, 200); await p.screenshot({path: `${out}/lib-3ds-${m}-mid.png`})
    await wait(p, 1500); await gp(p, 'dpad-right'); await wait(p, 1500)
  }
  await gp(p, 'r2'); await wait(p, 800)
  await gp(p, 'back'); await wait(p, 1800); await p.screenshot({path: `${out}/home-after-back.png`})
  await b.close()
})()
