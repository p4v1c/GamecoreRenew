/**
 * The overlay's lifecycle, run against the real `electron/main.js`.
 *
 * Electron itself is not started: the module is evaluated in a VM whose
 * `require('electron')` hands back doubles, so `BrowserWindow` records the
 * options it was given and the monitor's stdin is an array of what was
 * written. No native window, no emulator, no network.
 *
 * Two findings from the 2026-09-04 complementary audit:
 *
 *   16 — `overlay:start` awaits the backend before telling the monitor
 *        anything, and the game can be gone by the time that answer arrives.
 *        The cancelled start used to carry on and send `watch`, so the monitor
 *        reported on whatever window it found next.
 *   17 — the bezel window was pinned to (0, 0) 1920×1080 while the main window
 *        is genuinely fullscreen: on any other logical resolution that is a
 *        frame covering part of the picture, or one on the wrong output.
 *
 * Run:  node --test electron/test/
 */
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')

const MAIN = path.join(__dirname, '..', 'main.js')

/** A main.js with everything it talks to replaced. */
function rig({ display } = {}) {
  const ipc = new Map()
  const written = []
  const windows = []
  let resolveFetch
  const pending = new Promise((r) => { resolveFetch = r })

  class Window {
    constructor(options) {
      this.options = options
      windows.push(this)
      this.webContents = { isLoading: () => false, send: () => {}, once: () => {} }
    }
    setIgnoreMouseEvents() {}
    setAlwaysOnTop() {}
    setBounds() {}
    getBounds() { return { x: 0, y: 0, width: 1920, height: 1080 } }
    loadURL() {}
    on() {}
    close() {}
    show() {}
    hide() {}
    isVisible() { return true }
  }

  const child = { stdout: { on: () => {} }, stdin: { write: (s) => written.push(JSON.parse(s)) }, on: () => {} }
  const app = { commandLine: { appendSwitch: () => {} }, whenReady: () => ({ then: () => {} }), on: () => {}, quit: () => {} }
  const bounds = display || { x: 0, y: 0, width: 3840, height: 2160 }
  const electron = {
    app,
    BrowserWindow: Window,
    ipcMain: { on: (key, fn) => ipc.set(key, fn) },
    screen: { getPrimaryDisplay: () => ({ scaleFactor: 1, bounds, workAreaSize: { width: bounds.width, height: bounds.height } }) },
  }

  const stubs = {
    electron,
    'child_process': { spawn: () => child, exec: () => {} },
    fs: {
      existsSync: () => true,
      readFileSync: () => JSON.stringify({
        azahar: { window_rect: { x: 0, y: 0, w: 1920, h: 1080 }, hole: { x: 0, y: 0, w: 1920, h: 1080 } },
      }),
    },
    path,
    os: { uptime: () => 999 },
  }

  const context = vm.createContext({
    require: (id) => stubs[id],
    __dirname: path.dirname(MAIN),
    process: { env: {}, platform: 'linux', on: () => {} },
    console, setTimeout, clearTimeout, URLSearchParams, AbortSignal, AbortController,
    fetch: () => pending,
  })
  vm.runInContext(fs.readFileSync(MAIN, 'utf8'), context, { filename: MAIN })
  return { context, ipc, written, windows, resolveFetch }
}

test('a stop cancels a start that is still waiting on the backend', async () => {
  const r = rig()
  const starting = r.ipc.get('overlay:start')(null, { system_id: 'azahar', game_key: 'old.rom' })
  r.ipc.get('overlay:stop')(null, { system_id: 'azahar' })
  r.resolveFetch({
    ok: true,
    json: async () => ({ source: 'game', asset: '/assets/overlays/old.png', hole: { x: 0, y: 0, w: 1920, h: 1080 } }),
  })
  await starting
  assert.equal(r.written.filter((x) => x.cmd === 'watch').length, 0,
    'a cancelled launch was still handed to the monitor')
})

test('a start that is not cancelled does reach the monitor', async () => {
  const r = rig()
  const starting = r.ipc.get('overlay:start')(null, { system_id: 'azahar', game_key: 'live.rom' })
  r.resolveFetch({
    ok: true,
    json: async () => ({ source: 'game', asset: '/assets/overlays/live.png', hole: { x: 0, y: 0, w: 1920, h: 1080 } }),
  })
  await starting
  const watches = r.written.filter((x) => x.cmd === 'watch')
  assert.equal(watches.length, 1)
  assert.equal(watches[0].system_id, 'azahar')
})

test('the bezel window covers the display it is on, not 1080p', () => {
  const r = rig()
  r.context.createOverlayWindow()
  assert.equal(r.windows[0].options.width, 3840)
  assert.equal(r.windows[0].options.height, 2160)
})

test('and it follows a display that is not at the origin', () => {
  const r = rig({ display: { x: 1920, y: 0, width: 2560, height: 1440 } })
  r.context.createOverlayWindow()
  assert.deepEqual(
    { x: r.windows[0].options.x, y: r.windows[0].options.y,
      width: r.windows[0].options.width, height: r.windows[0].options.height },
    { x: 1920, y: 0, width: 2560, height: 1440 })
})
