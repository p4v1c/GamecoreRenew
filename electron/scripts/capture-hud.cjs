// node electron/scripts/capture-hud.cjs /absolute/output [baseline-ref]
// Real Chromium rendering, no Electron app, backend, display, or remote page.
const fs = require('node:fs')
const path = require('node:path')
const readCss = require('../test/css-bundle.cjs')
const os = require('node:os')
const { spawn, execFileSync } = require('node:child_process')
const rig = require('../test/hud-rig.cjs')
const contract = require('../hud-tokens.json')
const root = path.resolve(__dirname, '../..')
const out = path.resolve(process.argv[2] || '/tmp/gamecore-hud-captures')
const baseline = process.argv[3] || 'origin/main'
fs.mkdirSync(out, { recursive: true })
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'gc-hud-chromium-'))
const browser = spawn('chromium', ['--headless', '--disable-gpu', '--no-first-run',
  '--no-default-browser-check', '--disable-background-networking', '--disable-extensions',
  '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'],
  { env: { ...process.env, DISPLAY: '', WAYLAND_DISPLAY: '' }, stdio: ['ignore', 'ignore', 'pipe'] })
let socket
async function main() {
  const endpoint = await new Promise((resolve, reject) => {
    let log = ''
    browser.stderr.on('data', b => {
      log += b
      const m = log.match(/DevTools listening on (ws:\/\/[^\s]+)/)
      if (m) resolve(m[1])
    })
    browser.once('exit', code => reject(new Error(`Chromium exited ${code}: ${log}`)))
  })
  socket = new WebSocket(endpoint)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  let serial = 0
  const pending = new Map()
  socket.addEventListener('message', event => {
    const m = JSON.parse(event.data)
    if (!m.id) return
    const p = pending.get(m.id)
    if (!p) return
    clearTimeout(p.timer); pending.delete(m.id)
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result)
  })
  function send(method, params = {}, sessionId) {
    const id = ++serial
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`Timeout: ${method}`)), 15000)
      pending.set(id, { resolve, reject, timer })
      socket.send(JSON.stringify({ id, method, params, sessionId }))
    })
  }
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' })
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true })
  const call = (method, params) => send(method, params, sessionId)
  await call('Page.enable')
  await call('Emulation.setDefaultBackgroundColorOverride', { color: { r: 110, g: 128, b: 150, a: 0 } })
  async function document(html, width = 560, height = 240) {
    await call('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false })
    const { frameTree } = await call('Page.getFrameTree')
    await call('Page.setDocumentContent', { frameId: frameTree.frame.id, html })
    await call('Runtime.evaluate', { expression: 'document.fonts.ready', awaitPromise: true })
  }
  async function shot(file) {
    const { data } = await call('Page.captureScreenshot', { format: 'png' })
    fs.writeFileSync(path.join(out, file), Buffer.from(data, 'base64'))
  }
  const beforeSource = execFileSync('git', ['show', `${baseline}:electron/main.js`], { cwd: root, encoding: 'utf8' })
  const cases = [
    ['connected', 'notify:controller', { player: 1, connected: true, label: 'DualSense Wireless Controller' }],
    ['disconnected', 'notify:controller', { player: 1, connected: false, label: 'DualSense Wireless Controller' }],
    ['not-configured', 'notify:controller', { player: 1, connected: true, unconfigured: ['Nintendo Switch'] }],
    ['autoconfig-off', 'notify:controller', { player: 1, connected: true, autoconfigOff: ['Nintendo Switch'] }],
    ...[25, 15, 10, 5].map(level => [`battery-${level}`, 'notify:battery', { player: 1, level }]),
  ]
  const { build } = require('../../frontend/node_modules/esbuild')
  const preview = await build({
    stdin: { contents: `import React from 'react'; import { createRoot } from 'react-dom/client';
      import { DefaultToastsView } from './src/components/ui/Toasts';
      import { batteryNotice } from './src/components/ui/toasts/theme';
      createRoot(document.getElementById('root')).render(<DefaultToastsView onDismiss={() => {}} toasts={[
        {id:1, ...batteryNotice(25, 1)}, {id:2, ...batteryNotice(15, 1)},
        {id:3, ...batteryNotice(10, 1)}, {id:4, ...batteryNotice(5, 1)},
        {id:5, icon:'🕹️', title:'Controller 2 is not recognised',
         body:'Generic USB Gamepad is not in any controller database, so emulators cannot bind it. Map it once — about a minute, no keyboard.',
         accent:'#fbbf24', tone:'warning', action:{label:'Map it now',run:()=>{}}}
      ]} />);`, loader: 'tsx', resolveDir: path.join(root, 'frontend') },
    bundle: true, write: false, minify: true, define: { 'process.env.NODE_ENV': '"production"' },
  })
  const layout = []
  for (const name of ['none', 'orbit', 'shelf', 'summer']) {
    const css = name === 'none' ? '' : readCss(path.join(root, `config/themes/${name}/theme.css`))
    await document(`<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><style>${css}</style>`)
    const { result } = await call('Runtime.evaluate', {
      expression: `Object.fromEntries(${JSON.stringify(Object.keys(contract.tokens))}.map(k => [k, getComputedStyle(document.documentElement).getPropertyValue('--gc-hud-' + k).trim()]))`, returnByValue: true,
    })
    const theme = result.value
    fs.writeFileSync(path.join(out, `${name}-tokens.json`), JSON.stringify(theme, null, 2))
    const reactHTML = `<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#6e8096;font-family:sans-serif}${css}</style><div id="root"></div><script>${preview.outputFiles[0].text}</script>`
    fs.writeFileSync(path.join(out, `${name}-react.html`), reactHTML)
    await call('Emulation.setDeviceMetricsOverride', { width: 620, height: 1150, deviceScaleFactor: 1, mobile: false })
    await call('Page.navigate', { url: 'file://' + path.join(out, `${name}-react.html`) })
    await new Promise(resolve => setTimeout(resolve, 900))
    await shot(`${name}-react.png`)
    const rows = []
    for (const [kind, event, data] of cases) {
      const cells = []
      for (const version of ['before', 'after']) {
        const r = rig(version === 'before' ? beforeSource : undefined)
        r.ipc.get(event)(null, { ...data, theme })
        const w = r.windows[0]
        const file = `${name}-${kind}-${version}`
        fs.writeFileSync(path.join(out, file + '.html'), w.html)
        await document(w.html, w.options.width, w.options.height)
        const { result } = await call('Runtime.evaluate', {
          expression: `({height:document.body.firstElementChild.getBoundingClientRect().bottom, viewport:innerHeight})`, returnByValue: true,
        })
        layout.push({ name, kind, version, ...result.value })
        await shot(file + '.png')
        cells.push(`<td><img width="${w.options.width}" src="${file}.png"></td>`)
      }
      rows.push(`<tr><th>${kind}</th>${cells.join('')}</tr>`)
    }
    const gallery = `<!doctype html><meta charset="utf-8"><title>${name} HUD comparison</title><style>body{background:#d4dbe2;color:#17202d;font:16px sans-serif}table{border-collapse:collapse}td,th{padding:8px;text-align:left;vertical-align:top}img{display:block}td{background:#6e8096}h1{font-size:24px}</style><h1>${name} — native HUD, before / after</h1><table><tr><th>Event</th><th>Before</th><th>After</th></tr>${rows.join('')}</table>`
    fs.writeFileSync(path.join(out, name + '.html'), gallery)
    await call('Emulation.setDeviceMetricsOverride', { width: 1240, height: 2450, deviceScaleFactor: 1, mobile: false })
    await call('Page.navigate', { url: 'file://' + path.join(out, name + '.html') })
    // Wait for local images rather than sleeping or touching a real display.
    await new Promise(resolve => setTimeout(resolve, 300))
    await call('Runtime.evaluate', { expression: 'Promise.all([...document.images].map(i => i.decode()))', awaitPromise: true })
    await shot(name + '-comparison.png')
    console.log(`${name}: ${cases.length * 2} screenshots`)
  }
  fs.writeFileSync(path.join(out, 'layout.json'), JSON.stringify(layout, null, 2))
  fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><meta charset="utf-8"><h1>HUD comparisons</h1>' + ['none', 'orbit', 'shelf', 'summer'].map(n => `<p><a href="${n}.html">${n} — native before/after</a> · <a href="${n}-react.png">React and Map it now</a></p>`).join(''))
  await send('Browser.close')
}
main().catch(error => { console.error(error); process.exitCode = 1 }).finally(() => {
  socket?.close()
  browser.kill()
  browser.once('exit', () => fs.rmSync(profile, { recursive: true, force: true }))
})
