'use strict'
/**
 * The launch cover: one opaque window over the emulator while a game loads.
 *
 * The backend decides when (`game:loading`, then `game:ready`,
 * backend/services/launch_ready.py) and the renderer relays both here. The
 * page (`/cover`) draws the game's art and fades itself out; this file owns
 * the window. Not focusable, so the emulator under it keeps the keyboard and
 * the pads; at the bezel's level, so a fullscreen emulator cannot draw over it.
 *
 * Dependencies are handed in, so the VM bench can load this without Electron.
 */

// The page's fade (frontend/src/components/LaunchCover/launchCover.css) plus a frame.
const FADE_MS = 450
// Past the backend's own ceiling: a lost `game:ready` must never leave a
// running game hidden for good.
const SAFETY_MS = 15000
const DEFAULT_TIMEOUT_S = 90

function createCover({ BrowserWindow, bounds, pageUrl, preload,
                       setTimer = setTimeout, clearTimer = clearTimeout }) {
  let win = null
  let safety = null
  let leaving = null

  function close() {
    clearTimer(safety)
    clearTimer(leaving)
    safety = leaving = null
    const w = win
    win = null
    try { w?.close() } catch { /* already gone */ }
  }

  function show({ system_id = '', game_key = '', timeout_s } = {}) {
    close()
    const at = bounds()
    // Explicit geometry, not `fullscreen`: a fullscreen window lands in its
    // own compositor layer, under an emulator that asked for fullscreen too.
    win = new BrowserWindow({
      x: at.x, y: at.y, width: at.width, height: at.height,
      frame: false,
      // Transparent so the page's fade reveals the game, not a black window.
      transparent: true,
      backgroundColor: '#00000000',
      alwaysOnTop: true,
      skipTaskbar: true,
      focusable: false,
      show: false,
      webPreferences: {
        preload,
        nodeIntegration: false,
        contextIsolation: true,
        // The bezel's session: Display → Scale must not zoom this page.
        partition: 'gamecore-overlay',
      },
    })
    win.setIgnoreMouseEvents(true)
    win.setAlwaysOnTop(true, 'screen-saver')
    const q = new URLSearchParams({ system: system_id, rom: game_key })
    win.loadURL(`${pageUrl}?${q}`)
    // Shown at once rather than on `ready-to-show`: the cover goes up before
    // the spawn, so the page paints before the emulator maps a window.
    win.showInactive()
    const mine = win
    win.on('closed', () => { if (win === mine) win = null })
    const seconds = Number(timeout_s) > 0 ? Number(timeout_s) : DEFAULT_TIMEOUT_S
    safety = setTimer(close, seconds * 1000 + SAFETY_MS)
  }

  function hide() {
    if (!win || leaving) return
    try { win.webContents.send('cover:leave') } catch { /* page gone: close anyway */ }
    leaving = setTimer(close, FADE_MS)
  }

  function raise() {
    try { win?.moveTop() } catch { /* closed meanwhile */ }
  }

  return { show, hide, close, raise, isOpen: () => win !== null, window: () => win }
}

function register({ app, ipcMain, BrowserWindow, bounds, pageUrl, preload }) {
  const cover = createCover({ BrowserWindow, bounds, pageUrl, preload })
  ipcMain.on('cover:show', (_, data) => cover.show(data || {}))
  ipcMain.on('cover:hide', () => cover.hide())
  // The interface taking the screen back means no game is loading under us
  // (it ended, or was suspended): nothing is left to cover.
  ipcMain.on('shell:session-screen', (_, data) => { if (!data?.owned) cover.close() })
  // The bezel and the HUD share this level and arrive later: stay on top.
  app.on('browser-window-created', (_, w) => {
    if (!cover.isOpen() || w === cover.window()) return
    cover.raise()
    w.once?.('show', () => cover.raise())
  })
  return cover
}

module.exports = { createCover, register, FADE_MS, SAFETY_MS }
