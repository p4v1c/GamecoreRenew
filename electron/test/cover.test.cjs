/**
 * electron/cover.js: the launch cover's window. Electron is a double; no
 * window is drawn and the timers are manual.
 */
const assert = require('node:assert/strict')
const { test } = require('node:test')
const { createCover, register, FADE_MS, SAFETY_MS } = require('../cover.js')

function rig() {
  const windows = []
  const timers = []
  class Window {
    constructor(options) {
      this.options = options; this.calls = []; this.events = {}; this.sent = []; windows.push(this)
      this.webContents = {
        send: (ch, d) => this.sent.push([ch, d]),
        once: (ev, fn) => { this.events[`wc:${ev}`] = fn },
        on: (ev, fn) => { this.events[`wc:${ev}`] = fn },
      }
    }
    setIgnoreMouseEvents() {}
    setAlwaysOnTop(_on, level) { this.calls.push(`top:${level}`) }
    setBounds(b) { this.bounds = b }
    loadURL(url) { this.url = url }
    showInactive() { this.calls.push('showInactive') }
    hide() { this.calls.push('hide') }
    moveTop() { this.calls.push('moveTop') }
    on(ev, fn) { this.events[ev] = fn }
    close() { this.calls.push('close'); this.events.closed?.() }
    destroy() { this.calls.push('destroy') }
    loaded() { this.events['wc:did-finish-load']?.() }
    failed(code = -102) { this.events['wc:did-fail-load']?.({}, code, '', '', true) }
  }
  const setTimer = (fn, ms) => { const t = { fn, ms, done: false }; timers.push(t); return t }
  const clearTimer = (t) => { if (t) t.done = true }
  const fire = (ms) => timers.filter((t) => !t.done && t.ms === ms).forEach((t) => { t.done = true; t.fn() })
  const cover = createCover({ BrowserWindow: Window, bounds: () => ({ x: 0, y: 0, width: 3840, height: 2160 }),
                              pageUrl: 'http://127.0.0.1:8765/cover', preload: '/p.js', setTimer, clearTimer })
  return { cover, windows, timers, fire }
}

const sent = (w) => w.sent.map(([ch]) => ch)

test('warmed at start, hidden, so a launch does not wait for the page to load', () => {
  const { cover, windows } = rig()
  cover.warm()
  const [w] = windows
  assert.equal(w.options.show, false)
  assert.equal(w.options.focusable, false)
  assert.equal(w.options.webPreferences.backgroundThrottling, false)
  assert.equal(w.url, 'http://127.0.0.1:8765/cover')
  assert.ok(!w.calls.includes('showInactive'))
  w.loaded()
  cover.show({ system_id: 'rpcs3', game_key: 'Uncharted 2.sh', timeout_s: 240 })
  assert.equal(windows.length, 1, 'the warm window, not a new one')
  assert.deepEqual(w.sent[0], ['cover:game', { system: 'rpcs3', rom: 'Uncharted 2.sh' }])
  assert.ok(w.calls.includes('top:screen-saver'), 'above a fullscreen emulator')
  assert.ok(w.calls.includes('showInactive'))
  assert.equal(w.bounds.width, 3840, 'follows the display, not 1080p')
})

test('a launch before the page has loaded sends the game once it has', () => {
  const { cover, windows } = rig()
  cover.show({ system_id: 'switch', game_key: 'MK8.nsp' })
  const [w] = windows
  assert.deepEqual(w.sent, [])
  w.loaded()
  assert.deepEqual(w.sent, [['cover:game', { system: 'switch', rom: 'MK8.nsp' }]])
})

test('hiding fades the page, then parks the window for the next launch', () => {
  const { cover, windows, fire } = rig()
  cover.warm(); windows[0].loaded()
  cover.show({ system_id: 'rpcs3', game_key: 'G' })
  cover.hide()
  assert.deepEqual(sent(windows[0]), ['cover:game', 'cover:leave'])
  fire(FADE_MS)
  assert.deepEqual(sent(windows[0]), ['cover:game', 'cover:leave', 'cover:reset'])
  assert.ok(windows[0].calls.includes('hide'))
  assert.ok(!windows[0].calls.includes('close'), 'kept for the next launch')
  assert.equal(cover.isOpen(), false)
})

test('a lost signal still takes the cover down after the ceiling', () => {
  const { cover, windows, timers } = rig()
  cover.show({ system_id: 'switch', game_key: 'MK8.nsp', timeout_s: 180 })
  const safety = timers.find((t) => t.ms === 180 * 1000 + SAFETY_MS)
  assert.ok(safety, 'safety timer from the backend ceiling')
  safety.fn()
  assert.ok(windows[0].calls.includes('hide'))
  assert.equal(cover.isOpen(), false)
})

test('a second launch reuses the window with the new game', () => {
  const { cover, windows } = rig()
  cover.warm(); windows[0].loaded()
  cover.show({ system_id: 'a', game_key: 'A' })
  cover.show({ system_id: 'b', game_key: 'B' })
  assert.equal(windows.length, 1)
  assert.deepEqual(sent(windows[0]), ['cover:game', 'cover:reset', 'cover:game'])
  assert.deepEqual(windows[0].sent[2][1], { system: 'b', rom: 'B' })
})

test('a page that failed to load (backend not up yet) is made again at the launch', () => {
  const { cover, windows } = rig()
  cover.warm()
  windows[0].failed()              // ERR_CONNECTION_REFUSED at boot
  assert.ok(windows[0].calls.includes('destroy'))
  cover.show({ system_id: 'rpcs3', game_key: 'G' })
  assert.equal(windows.length, 2, 'a fresh window, not the dead page')
  windows[1].loaded()
  assert.deepEqual(windows[1].sent, [['cover:game', { system: 'rpcs3', rom: 'G' }]])
})

test('a superseded load is not a failure', () => {
  const { cover, windows } = rig()
  cover.warm()
  windows[0].failed(-3)
  assert.ok(!windows[0].calls.includes('destroy'))
  assert.equal(cover.window(), windows[0])
})

test('a window that was closed is made again on the next launch', () => {
  const { cover, windows } = rig()
  cover.warm()
  windows[0].close()
  cover.show({ system_id: 'rpcs3', game_key: 'G' })
  assert.equal(windows.length, 2)
  assert.ok(windows[1].calls.includes('showInactive'))
})

test('the interface coming back takes it down, and a later window does not cover it', async () => {
  const ipc = new Map()
  const appEvents = {}
  const windows = []
  class Window {
    constructor() { this.calls = []; windows.push(this); this.webContents = { send: () => {}, once: () => {}, on: () => {} } }
    setIgnoreMouseEvents() {} setAlwaysOnTop() {} setBounds() {} loadURL() {} showInactive() {} on() {}
    hide() { this.calls.push('hide') }
    moveTop() { this.calls.push('moveTop') }
    close() { this.calls.push('close') }
  }
  let ready
  register({ app: { on: (ev, fn) => { appEvents[ev] = fn }, whenReady: () => new Promise((r) => { ready = r }) },
             ipcMain: { on: (k, fn) => ipc.set(k, fn) }, BrowserWindow: Window,
             bounds: () => ({ x: 0, y: 0, width: 1920, height: 1080 }), pageUrl: '/cover', preload: '' })
  ready()
  await new Promise((r) => setImmediate(r))
  assert.equal(windows.length, 1, 'warmed once the app is ready')
  ipc.get('cover:show')({}, { game_key: 'G' })
  const bezel = { once: (ev, fn) => { if (ev === 'show') fn() } }
  appEvents['browser-window-created']({}, bezel)
  assert.deepEqual(windows[0].calls, ['moveTop', 'moveTop'])
  ipc.get('shell:session-screen')({}, { owned: true })
  assert.ok(!windows[0].calls.includes('hide'), 'a game taking the screen keeps the cover')
  ipc.get('shell:session-screen')({}, { owned: false })
  assert.ok(windows[0].calls.includes('hide'))
})
