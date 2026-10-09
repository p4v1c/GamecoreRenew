// YouTube suspended in the background (session faked by intercepting /api/games/session).
const {open, wait, focusHome, gp} = require('./lib.cjs')
;(async () => {
  const out = process.argv[2]
  const {b, p} = await open({session: {background: [{game_key: 'youtube', system_id: 'youtube', session: 7, state: 'background', kind: 'app'}]}})
  await focusHome(p, 'youtube'); await wait(p, 900)
  await p.screenshot({path: `${out}/home-youtube-held.png`})
  await gp(p, 'y'); await wait(p, 400)
  await p.screenshot({path: `${out}/home-youtube-held-armed.png`})
  const ledge = await p.evaluate(() => { const e = document.querySelector('.cz-session'); return e && JSON.stringify(e.getBoundingClientRect()) })
  console.log('ledge', ledge)
  await b.close()
})()
