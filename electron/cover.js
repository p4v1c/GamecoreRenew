'use strict'
/**
 * The launch cover: one opaque window over the emulator while a game loads.
 *
 * The backend decides when (`game:loading`, then `game:ready`,
 * backend/services/launch_ready.py) and the renderer relays both here. The
 * page (`/cover`) draws the game's art and fades itself in and out; this file
 * owns the window. Not focusable, so the emulator under it keeps the keyboard
 * and the pads; at the bezel's level, so a fullscreen emulator cannot draw
 * over it.
 *
 * One window, made hidden at start and reused: a window made at launch time
 * spent the first second loading the interface's bundle, and the emulator
 * could map its own window before the cover was up.
 *
 * Dependencies are handed in, so the VM bench can load this without Electron.
 */

// The page's leave (frontend/src/components/LaunchCover/launchCover.css):
// art to black, then black to the game, plus a frame.
const FADE_MS = 950
// Past the backend's own ceiling: a lost `game:ready` must never leave a
// running game hidden for good.
const SAFETY_MS = 15000
const DEFAULT_TIMEOUT_S = 90

function createCover({ BrowserWindow, bounds, pageUrl, preload,
                       setTimer = setTimeout, clearTimer = clearTimeout }) {
  let win = null
  let loaded = false
  let queued = null     // the game to send once the page has loaded
  let up = false
  let safety = null
  let leaving = null

  function make() {
    const at = bounds()
    // Explicit geometry, not `fullscreen`: a fullscreen window lands in its
    // own compositor layer, under an emulator that asked for fullscreen too.
    win = new BrowserWindow({
      x: at.x, y: at.y, width: at.width, height: at.height,
      frame: false,
      // Transparent so the page's fades show what is under it.
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
        // Hidden until a launch: it must still be ready to paint at once.
        backgroundThrottling: false,
      },
    })
    win.setIgnoreMouseEvents(true)
    win.setAlwaysOnTop(true, 'screen-saver')
    loaded = false
    const mine = win
    win.webContents.once?.('did-finish-load', () => {
      if (win !== mine) return
      loaded = true
      if (queued) send('cover:game', queued)
      queued = null
    })
    // Made at start, often before the backend answers: a page that failed to
    // load would never get its game. Dropped, it is made again at the launch.
    win.webContents.on?.('did-fail-load', (_e, code, _desc, _url, mainFrame) => {
      if (win !== mine || !mainFrame || code === -3) return   // -3: superseded
      win = null
      up = false
      try { mine.destroy() } catch { /* already gone */ }
    })
    win.on('closed', () => { if (win === mine) { win = null; up = false } })
    win.loadURL(pageUrl)
  }

  function send(channel, data) {
    try { win?.webContents.send(channel, data) } catch { /* page gone */ }
  }

  /** The page cleared and the window hidden, ready for the next launch. */
  function park() {
    clearTimer(safety)
    clearTimer(leaving)
    safety = leaving = null
    if (!up) return
    up = false
    send('cover:reset')
    try { win?.hide() } catch { /* closed meanwhile */ }
  }

  function show({ system_id = '', game_key = '', timeout_s } = {}) {
    park()
    if (!win) make()
    const at = bounds()
    try { win.setBounds?.(at) } catch { /* keeps the size it was made with */ }
    const game = { system: system_id, rom: game_key }
    if (loaded) send('cover:game', game)
    else queued = game
    // Shown at once: the page stays transparent until its art is decoded,
    // then fades in, so the launch ceremony is what shows until then.
    win.setAlwaysOnTop(true, 'screen-saver')
    win.showInactive()
    up = true
    const seconds = Number(timeout_s) > 0 ? Number(timeout_s) : DEFAULT_TIMEOUT_S
    safety = setTimer(park, seconds * 1000 + SAFETY_MS)
  }

  function hide() {
    if (!up || leaving) return
    send('cover:leave')
    leaving = setTimer(park, FADE_MS)
  }

  function raise() {
    try { win?.moveTop() } catch { /* closed meanwhile */ }
  }

  return { show, hide, close: park, raise, warm: () => { if (!win) make() },
           isOpen: () => up, window: () => win }
}

function register({ app, ipcMain, BrowserWindow, bounds, pageUrl, preload }) {
  const cover = createCover({ BrowserWindow, bounds, pageUrl, preload })
  app.whenReady?.().then(() => cover.warm()).catch(() => { /* made on first launch */ })
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
