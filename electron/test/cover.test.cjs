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
    constructor(options) { this.options = options; this.calls = []; this.events = {}; windows.push(this)
      this.webContents = { send: (ch) => this.calls.push(`send:${ch}`) } }
    setIgnoreMouseEvents() {}
    setAlwaysOnTop(_on, level) { this.calls.push(`top:${level}`) }
    loadURL(url) { this.url = url }
    showInactive() { this.calls.push('showInactive') }
    moveTop() { this.calls.push('moveTop') }
    on(ev, fn) { this.events[ev] = fn }
    close() { this.calls.push('close'); this.events.closed?.() }
  }
  const setTimer = (fn, ms) => { const t = { fn, ms, done: false }; timers.push(t); return t }
  const clearTimer = (t) => { if (t) t.done = true }
  const fire = (ms) => timers.filter((t) => !t.done && t.ms === ms).forEach((t) => { t.done = true; t.fn() })
  const cover = createCover({ BrowserWindow: Window, bounds: () => ({ x: 0, y: 0, width: 3840, height: 2160 }),
                              pageUrl: 'http://127.0.0.1:8765/cover', preload: '/p.js', setTimer, clearTimer })
  return { cover, windows, timers, fire }
}

test('the cover opens over the emulator without taking the focus', () => {
  const { cover, windows } = rig()
  cover.show({ system_id: 'rpcs3', game_key: 'Uncharted 2.sh', timeout_s: 240 })
  const [w] = windows
  assert.equal(w.options.focusable, false)
  assert.equal(w.options.width, 3840, 'follows the display, not 1080p')
  assert.ok(w.calls.includes('top:screen-saver'), 'above a fullscreen emulator')
  assert.ok(w.calls.includes('showInactive'))
  assert.equal(w.url, 'http://127.0.0.1:8765/cover?system=rpcs3&rom=Uncharted+2.sh')
})

test('hiding fades the page, then closes the window', () => {
  const { cover, windows, fire } = rig()
  cover.show({ system_id: 'rpcs3', game_key: 'G' })
  cover.hide()
  assert.deepEqual(windows[0].calls.filter((c) => c.startsWith('send') || c === 'close'), ['send:cover:leave'])
  fire(FADE_MS)
  assert.ok(windows[0].calls.includes('close'))
  assert.equal(cover.isOpen(), false)
})

test('a lost signal still closes the cover after the ceiling', () => {
  const { cover, windows, timers } = rig()
  cover.show({ system_id: 'switch', game_key: 'MK8.nsp', timeout_s: 180 })
  const safety = timers.find((t) => t.ms === 180 * 1000 + SAFETY_MS)
  assert.ok(safety, 'safety timer from the backend ceiling')
  safety.fn()
  assert.ok(windows[0].calls.includes('close'))
})

test('a second launch replaces the first cover', () => {
  const { cover, windows } = rig()
  cover.show({ game_key: 'A' })
  cover.show({ game_key: 'B' })
  assert.ok(windows[0].calls.includes('close'))
  assert.equal(cover.window(), windows[1])
})

test('the interface coming back closes it, and a later window does not cover it', () => {
  const ipc = new Map()
  const appEvents = {}
  const windows = []
  class Window {
    constructor() { this.calls = []; windows.push(this); this.webContents = { send: () => {} } }
    setIgnoreMouseEvents() {} setAlwaysOnTop() {} loadURL() {} showInactive() {} on() {}
    moveTop() { this.calls.push('moveTop') }
    close() { this.calls.push('close') }
  }
  register({ app: { on: (ev, fn) => { appEvents[ev] = fn } },
             ipcMain: { on: (k, fn) => ipc.set(k, fn) }, BrowserWindow: Window,
             bounds: () => ({ x: 0, y: 0, width: 1920, height: 1080 }), pageUrl: '/cover', preload: '' })
  ipc.get('cover:show')({}, { game_key: 'G' })
  const bezel = { once: (ev, fn) => { if (ev === 'show') fn() } }
  appEvents['browser-window-created']({}, bezel)
  assert.deepEqual(windows[0].calls, ['moveTop', 'moveTop'])
  ipc.get('shell:session-screen')({}, { owned: true })
  assert.ok(!windows[0].calls.includes('close'), 'a game taking the screen keeps the cover')
  ipc.get('shell:session-screen')({}, { owned: false })
  assert.ok(windows[0].calls.includes('close'))
})
