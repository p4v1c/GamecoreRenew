// Home screenshots: node home-shots.cjs <outdir> <id>[:name] ...
const {open, wait, focusHome} = require('./lib.cjs')
;(async () => {
  const [out, ...targets] = process.argv.slice(2)
  const {b, p} = await open()
  for (const t of targets) {
    const [id, name] = t.split(':')
    await focusHome(p, id)
    await wait(p, 900)
    await p.screenshot({path: `${out}/${name || 'home-' + id}.png`})
    console.log('shot', id)
  }
  await b.close()
})()
