/**
 * The boot, driven against the real `electron/main.js`.
 *
 * Two things are asserted, and they are the two the shell used to get wrong:
 *
 *   · **who owns the backend.** On an installed box systemd does. Electron
 *     spawning a second uvicorn on the same port produced an EADDRINUSE crash
 *     loop next to a working backend, and the guard against it — "nothing
 *     answered in the last 1.5 s" — is true of a backend that is merely still
 *     starting.
 *   · **what "ready" means.** `/api/sysinfo` answers while the backend is
 *     still opening its database, so "alive" arrived seconds before "usable",
 *     and the window was created against a backend that could not serve it.
 *
 * Electron, the child processes and the network are doubles; no window is
 * created and no process is spawned.
 */
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')

const MAIN = path.join(__dirname, '..', 'main.js')

/**
 * @param answers  the sequence /api/ready gives back, `true` = 200 {ready}
 * @param env      the process environment main.js sees
 */
function rig({ answers = [true], env = {} } = {}) {
  const windows = []
  const spawned = []
  const ipc = new Map()
  const asked = []
  let readyResolve
  const appReady = new Promise((r) => { readyResolve = r })

  class Window {
    constructor(options) {
      this.options = options
      this.loaded = []          // every document this window was given, in order
      this.shown = false
      this.handlers = new Map()
      windows.push(this)
      // `on` as well as `once`: the window listens for a renderer that dies.
      this.rendererHandlers = new Map()
      this.webContents = {
        isLoading: () => false, send: () => {}, once: () => {}, openDevTools: () => {},
        on: (event, fn) => this.rendererHandlers.set(event, fn),
      }
    }
    setIgnoreMouseEvents() {} setAlwaysOnTop() {} setBounds() {}
    getBounds() { return { x: 0, y: 0, width: 1920, height: 1080 } }
    loadFile(p) { this.loaded.push({ kind: 'file', at: p }) }
    loadURL(u) { this.loaded.push({ kind: 'url', at: u }) }
    once(event, fn) { this.handlers.set(event, fn) }
    on() {} close() {} hide() {} isVisible() { return true }
    show() { this.shown = true }
    /** What Electron does once the first document can be painted. */
    readyToShow() { this.handlers.get('ready-to-show')?.() }
    /** What Electron does when the renderer process dies. */
    rendererGone(reason = 'crashed') {
      this.rendererHandlers.get('render-process-gone')?.({}, { reason })
    }
  }

  const child = { stdout: { on: () => {} }, stdin: { write: () => {} }, on: () => {} }
  const electron = {
    app: {
      commandLine: { appendSwitch: () => {} },
      whenReady: () => appReady,
      on: () => {}, quit: () => {},
    },
    BrowserWindow: Window,
    ipcMain: { on: (key, fn) => ipc.set(key, fn) },
    screen: { getPrimaryDisplay: () => ({ scaleFactor: 1, bounds: { x: 0, y: 0, width: 1920, height: 1080 } }) },
  }

  const stubs = {
    electron,
    'child_process': { spawn: (bin, args) => { spawned.push({ bin, args }); return child }, exec: () => {} },
    fs: { existsSync: () => true, readFileSync: () => '{}' },
    path,
    os: { uptime: () => 999 },
  }

  const queue = answers.slice()
  const context = vm.createContext({
    require: (id) => stubs[id],
    __dirname: path.dirname(MAIN),
    process: { env },
    console: { log: () => {}, warn: () => {}, error: () => {} },
    setTimeout, clearTimeout, URLSearchParams, AbortSignal, AbortController,
    fetch: (url) => {
      asked.push(String(url))
      const ok = queue.length > 1 ? queue.shift() : queue[0]
      return Promise.resolve({ ok, status: ok ? 200 : 503, json: async () => ({ ready: !!ok, state: ok ? 'ready' : 'starting' }) })
    },
  })
  vm.runInContext(fs.readFileSync(MAIN, 'utf8'), context, { filename: MAIN })
  return {
    context, windows, ipc, asked,
    // The overlay monitor is a legitimate child; only a second uvicorn is the
    // defect this file is about.
    backends: () => spawned.filter(s => s.args.join(' ').includes('uvicorn')),
    start: () => { readyResolve(); return appReady },
    // The wait for a backend deliberately has no deadline — it slows down and
    // reports, it never gives up. Ending the generation is how a test stops it
    // without the code learning to abandon a boot.
    stop: () => vm.runInContext('bootGeneration += 1', context),
  }
}

/** Let the boot's promise chain and its polling run. */
const settle = (ms = 60) => new Promise(r => setTimeout(r, ms))

test('the screen is covered before anything is waited for', async () => {
  // The order is the whole visible change. The window used to be created after
  // the backend answered, so what covered the television during that wait was
  // the desktop: wallpaper, panel, and whatever was left open.
  const r = rig({ answers: [false], env: { INVOCATION_ID: 'x' } })
  r.start()
  await settle(120)
  r.stop()
  assert.equal(r.windows.length, 1, 'nothing was on screen while the backend started')
  const first = r.windows[0].loaded[0]
  assert.equal(first.kind, 'file', 'the first document came from the network')
  assert.match(first.at, /boot[\\/]boot\.html$/)
  assert.equal(r.windows[0].options.show, false, 'a window shown before its first paint is a white flash')
})

test('the interface replaces the boot screen in the same window', async () => {
  // A second window would be a second thing for the compositor to stack and
  // to focus, and neither is this code's decision to make.
  const r = rig({ answers: [true], env: { INVOCATION_ID: 'x' } })
  r.start()
  await settle(200)
  r.stop()
  assert.equal(r.windows.length, 1)
  const kinds = r.windows[0].loaded.map(l => l.kind)
  assert.deepEqual(kinds, ['file', 'url'])
})

test('a backend that never answers leaves the boot screen up', async () => {
  const r = rig({ answers: [false], env: { INVOCATION_ID: 'x' } })
  r.start()
  await settle(900)
  r.stop()
  assert.deepEqual(r.windows[0].loaded.map(l => l.kind), ['file'],
    'the interface was loaded over a backend that cannot serve it')
})

test('the window is shown when it has something to show', async () => {
  const r = rig({ answers: [false], env: { INVOCATION_ID: 'x' } })
  r.start()
  await settle(120)
  r.stop()
  assert.equal(r.windows[0].shown, false)
  r.windows[0].readyToShow()
  assert.equal(r.windows[0].shown, true)
})

test('a managed box never starts a second backend', async () => {
  // INVOCATION_ID is what systemd sets in every service it runs; start-ui.sh is
  // the unit's ExecStart, so Electron inherits it.
  const r = rig({ answers: [false, false, true], env: { INVOCATION_ID: 'abc123' } })
  r.start()
  await settle(900)
  r.stop()
  assert.deepEqual(r.backends(), [], 'Electron competed with systemd for the port')
})

test('an unmanaged box still starts one when nothing answers', async () => {
  const r = rig({ answers: [false, false, true], env: {} })
  r.start()
  await settle(900)
  r.stop()
  assert.equal(r.backends().length, 1)
})

test('readiness is asked of /api/ready, not of the diagnostic endpoint', async () => {
  const r = rig({ answers: [true], env: { INVOCATION_ID: 'x' } })
  r.start()
  await settle(200)
  r.stop()
  assert.ok(r.asked.length > 0)
  assert.ok(r.asked.every(u => u.includes('/api/ready')), r.asked.join(' '))
  assert.ok(!r.asked.some(u => u.includes('/api/sysinfo')))
})

test('the interface saying it is ready is what ends the boot', async () => {
  const r = rig({ answers: [true], env: { INVOCATION_ID: 'x' } })
  r.start()
  await settle(200)
  r.stop()
  assert.equal(typeof r.ipc.get('boot:ready'), 'function',
    'the host has no way to say the interface is ready')
  r.ipc.get('boot:ready')(null, { steps: { theme: true, systems: true } })
})

test('the boot screen needs nothing but itself', () => {
  // It is what covers the television when the backend is down, the network is
  // absent and the bundle has not been built. Anything it has to fetch is a
  // way for it to fail at exactly the moment it exists for.
  const html = fs.readFileSync(path.join(__dirname, '..', 'boot', 'boot.html'), 'utf8')
  assert.ok(!/https?:\/\//i.test(html), 'the boot screen reaches for the network')
  assert.ok(!/<script/i.test(html), 'a boot screen that can hang is not a boot screen')
  assert.ok(!/src=|href=/i.test(html), 'the boot screen loads a file of its own')
})

test('a renderer that dies puts the boot screen back', async () => {
  // What is left otherwise is a window showing the last frame it painted: a
  // console that looks frozen rather than broken, with no way back but the
  // power switch.
  const r = rig({ answers: [true], env: { INVOCATION_ID: 'x' } })
  r.start()
  await settle(200)
  const window = r.windows[0]
  assert.deepEqual(window.loaded.map(l => l.kind), ['file', 'url'])

  window.rendererGone('crashed')
  await settle(200)
  r.stop()
  assert.deepEqual(window.loaded.map(l => l.kind), ['file', 'url', 'file', 'url'],
    'the boot screen did not come back, or the interface never returned')
})
