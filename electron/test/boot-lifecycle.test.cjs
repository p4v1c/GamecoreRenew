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
      windows.push(this)
      this.webContents = { isLoading: () => false, send: () => {}, once: () => {}, openDevTools: () => {} }
    }
    setIgnoreMouseEvents() {} setAlwaysOnTop() {} setBounds() {}
    getBounds() { return { x: 0, y: 0, width: 1920, height: 1080 } }
    loadURL() {} on() {} close() {} show() {} hide() {} isVisible() { return true }
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

test('a managed box never starts a second backend', async () => {
  // INVOCATION_ID is what systemd sets in every service it runs; start-ui.sh is
  // the unit's ExecStart, so Electron inherits it.
  const r = rig({ answers: [false, false, true], env: { INVOCATION_ID: 'abc123' } })
  r.start()
  await settle(900)
  r.stop()
  assert.deepEqual(r.backends(), [], 'Electron competed with systemd for the port')
  assert.equal(r.windows.length, 1, 'the window was never created')
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

test('a backend that only answers 503 gets no window at all', async () => {
  // "Not yet" must never be read as "carry on": carrying on means a home
  // screen built from nothing, which is the outcome this step exists to stop.
  const r = rig({ answers: [false], env: { INVOCATION_ID: 'x' } })
  r.start()
  await settle(900)
  r.stop()
  assert.equal(r.windows.length, 0, 'the interface was shown over a backend that cannot serve it')
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
