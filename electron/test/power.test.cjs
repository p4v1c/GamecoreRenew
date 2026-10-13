/**
 * electron/power.js: the reboot/shutdown commands, and the window after a wake.
 * Electron is a double; nothing is suspended or rebooted.
 */
const assert = require('node:assert/strict')
const { test } = require('node:test')
const { registerPowerIpc, watchResume } = require('../power.js')

function fakeWindow({ fullscreen = false } = {}) {
  const calls = []
  return {
    calls,
    isFullScreen: () => fullscreen,
    setFullScreen: (v) => { fullscreen = v; calls.push(`fullscreen:${v}`) },
    show: () => calls.push('show'),
    focus: () => calls.push('focus'),
  }
}

function fakeMonitor() {
  const handlers = new Map()
  return { on: (ev, fn) => handlers.set(ev, fn), emit: (ev) => handlers.get(ev)?.() }
}

test('reboot and shutdown run the commands sudoers grants', () => {
  const ipc = new Map()
  const execs = []
  registerPowerIpc({ ipcMain: { on: (k, fn) => ipc.set(k, fn) }, exec: (c) => execs.push(c) })
  ipc.get('system:reboot')()
  ipc.get('system:shutdown')()
  assert.deepEqual(execs, ['sudo systemctl reboot', 'sudo systemctl poweroff'])
})

test('a wake puts the interface back in fullscreen and focused', () => {
  const win = fakeWindow({ fullscreen: false })
  const monitor = fakeMonitor()
  watchResume({ powerMonitor: monitor, getWindow: () => win,
                sessionOwnsScreen: () => false, log: () => {} })
  monitor.emit('resume')
  assert.deepEqual(win.calls, ['fullscreen:true', 'show', 'focus'])
})

test('a wake leaves a session that owns the screen alone', () => {
  const win = fakeWindow()
  const monitor = fakeMonitor()
  watchResume({ powerMonitor: monitor, getWindow: () => win,
                sessionOwnsScreen: () => true, log: () => {} })
  monitor.emit('resume')
  assert.deepEqual(win.calls, [])
})

test('an Electron without powerMonitor is not an error', () => {
  assert.equal(watchResume({ powerMonitor: undefined, getWindow: () => null,
                             sessionOwnsScreen: () => false }), false)
})
