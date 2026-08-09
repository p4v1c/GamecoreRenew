'use strict'
const { app, BrowserWindow, ipcMain, screen, session } = require('electron')
const { exec, spawn } = require('child_process')
const path = require('path')
const fs   = require('fs')
const os   = require('os')

// Required on Linux X11 for per-pixel transparency in BrowserWindow
app.commandLine.appendSwitch('enable-transparent-visuals')

// Chromium keeps WebAudio suspended until a "user gesture" — and gamepad
// buttons don't count as one (only mouse/keyboard do). On a controller-only
// kiosk the UI sounds would stay silent forever without this.
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required')

const DEBUG = false

const DEV = DEBUG && process.env.ELECTRON_DEV === '1'
// The installer lets the operator pick the backend port and passes it through
// gamecore-ui.service (Environment=GAMECORE_BACKEND_PORT). Hardcoding 8765
// here meant any other choice left the kiosk on a permanent black screen.
const BACKEND_PORT = process.env.GAMECORE_BACKEND_PORT || '8765'
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`
const DEV_URL     = 'http://localhost:5173'

let mainWindow     = null
let backendProcess = null
let overlayWindow  = null

// Set only by Settings → Desktop (system:quit). Everything else that empties
// the window list is a fault, and window-all-closed rebuilds instead of dying.
let quitting = false
// Timestamps of recent rebuilds. A kiosk must never exit on its own, but it
// must not spin either: if the window cannot stay up, stop and let systemd and
// the desktop launcher deal with it.
let rebuilds = []
const REBUILD_LIMIT  = 3
const REBUILD_WINDOW = 10_000
let monitorProcess = null

// At cold boot the UI loads while the display path is still black — X just
// started, gamecore-xsetup switches the mode to 1080p and the TV spends a few
// seconds re-syncing HDMI. The splash animation would play unseen during that
// window (the user only catches the tail of it). So when the machine booted
// recently, ask the splash to hold its first (black) frame before starting
// the timeline. A relaunch from the desktop (uptime is high) gets no delay.
const BOOT_UPTIME_THRESHOLD_S = 180
const SPLASH_BOOT_HOLD_MS     = 4000

function splashHoldMs() {
  return os.uptime() < BOOT_UPTIME_THRESHOLD_S ? SPLASH_BOOT_HOLD_MS : 0
}

// ── Main window ───────────────────────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1920,
    height: 1080,
    fullscreen: true,
    kiosk: !DEBUG && !DEV,
    frame: false,
    autoHideMenuBar: true,
    backgroundColor: '#09090f',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: true,
      // This window is the WebSocket bridge for battery alerts even while
      // buried under an emulator or hidden behind a bezel overlay — never
      // let Chromium throttle it in the background.
      backgroundThrottling: false,
    },
  })

  const holdParam = `?splashHold=${splashHoldMs()}`
  if (DEV) {
    mainWindow.loadURL(DEV_URL + holdParam)
  } else {
    mainWindow.loadURL(BACKEND_URL + holdParam)
  }

  if (DEBUG) mainWindow.webContents.openDevTools({ mode: 'detach' })

  mainWindow.on('closed', () => { mainWindow = null })
}

// ── Overlay window ────────────────────────────────────────────────────────────
function createOverlayWindow() {
  if (overlayWindow) return

  overlayWindow = new BrowserWindow({
    x: 0,
    y: 0,
    width: 1920,
    height: 1080,
    // Do NOT use fullscreen: true — on Linux X11 fullscreen windows are placed
    // in a separate compositor layer that prevents see-through transparency.
    // Explicit x/y/w/h with alwaysOnTop gives the same visual result.
    transparent: true,
    backgroundColor: '#00000000',
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    focusable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: true,
    },
  })

  overlayWindow.setIgnoreMouseEvents(true)
  // `alwaysOnTop: true` alone is the "floating" level, and KWin puts a window
  // that asked for _NET_WM_STATE_FULLSCREEN — which is what every emulator
  // launched with -f does — in a layer above it. The bezel then draws *under*
  // the emulator and only shows where the emulator happens not to paint.
  // Measured with Rosalie's Mupen GUI: two 1920x1080 RMG windows on top, the
  // bezel visible only in the two vertical strips RMG leaves untouched.
  overlayWindow.setAlwaysOnTop(true, 'screen-saver')

  // Open DevTools for the overlay window so we can inspect its DOM
  if (DEBUG) overlayWindow.webContents.openDevTools({ mode: 'detach' })

  const overlayUrl = DEV
    ? `${DEV_URL}/overlay`
    : `${BACKEND_URL}/overlay`
  overlayWindow.loadURL(overlayUrl)

  overlayWindow.on('closed', () => { overlayWindow = null })
}

function destroyOverlayWindow() {
  if (overlayWindow) {
    overlayWindow.close()
    overlayWindow = null
  }
}

// ── HUD toasts (battery, controller connect/disconnect) ───────────────────────
// In-game the main window is buried under the fullscreen emulator, so its
// React toast is invisible. This small transparent always-on-top window
// (same recipe as the bezel overlay) shows the alert over anything.
let hudToastWindow = null
let hudToastTimer  = null
const HUD_TOAST_MS = 10000

// title/body/label reach us from the renderer over IPC, and the renderer gets
// them from WebSocket broadcasts — including /api/addons/notify, an open LAN
// endpoint, and Bluetooth device names. Never interpolate them into HTML raw.
function escHtml(s) {
  return String(s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ))
}

// accent lands inside style="" — only ever use it as a plain color token
function safeColor(c) {
  return /^#[0-9a-fA-F]{3,8}$/.test(String(c)) ? c : '#fbbf24'
}

function showHudToast({ icon = '🎮', title = '', body = '', accent = '#fbbf24' } = {}) {
  icon = escHtml(icon); title = escHtml(title); body = escHtml(body)
  accent = safeColor(accent)
  const html = `<!doctype html><html><body style="margin:0;background:transparent;overflow:hidden;font-family:sans-serif">
    <div style="display:flex;align-items:center;gap:14px;margin:8px;padding:14px 18px;border-radius:14px;
                background:rgba(18,18,26,0.94);border:1px solid ${accent};box-shadow:0 8px 32px rgba(0,0,0,0.6)">
      <div style="width:40px;height:40px;border-radius:10px;background:${accent}33;display:flex;align-items:center;justify-content:center;font-size:20px">${icon}</div>
      <div>
        <div style="font-size:14px;font-weight:700;color:${accent}">${title}</div>
        <div style="font-size:13px;color:rgba(255,255,255,0.7);margin-top:3px">${body}</div>
      </div>
    </div></body></html>`

  if (hudToastTimer) { clearTimeout(hudToastTimer); hudToastTimer = null }
  // destroy(), not close(): close() is a request that can be ignored — a
  // lingering HUD on screen is worse than a skipped fade-out.
  if (hudToastWindow) { hudToastWindow.destroy(); hudToastWindow = null }

  const { width } = screen.getPrimaryDisplay().workAreaSize
  const W = 440, H = 100
  hudToastWindow = new BrowserWindow({
    // Below the TopBar (54px tall) so the HUD never covers the battery/IP/
    // settings pills when it pops over the menu.
    x: width - W - 24, y: 66, width: W, height: H,
    transparent: true, backgroundColor: '#00000000', frame: false,
    alwaysOnTop: true, skipTaskbar: true, focusable: false,
    resizable: false, hasShadow: false,
    webPreferences: { nodeIntegration: false, contextIsolation: true },
  })
  hudToastWindow.setIgnoreMouseEvents(true)
  hudToastWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html))
  // Both this window and the bezel overlay are always-on-top: X11 stacks the
  // most recently raised one higher, but make it explicit so the alert can
  // never end up under the bezel.
  hudToastWindow.webContents.once('did-finish-load', () => {
    hudToastWindow?.moveTop()
  })
  hudToastWindow.on('closed', () => { hudToastWindow = null })

  hudToastTimer = setTimeout(() => {
    hudToastTimer = null
    if (hudToastWindow) { hudToastWindow.destroy(); hudToastWindow = null }
  }, HUD_TOAST_MS)
}

function showBatteryToast({ level = 0, player = null } = {}) {
  const accent = level <= 5 ? '#ef4444' : '#fbbf24'
  const who = player ? `Controller ${player}` : 'Controller'
  showHudToast({
    icon: '🎮',
    title: `${who} battery low`,
    body: `${who} has ${Math.round(Number(level))}% battery left`,
    accent,
  })
}

ipcMain.on('notify:battery', (_, data) => showBatteryToast(data || {}))

ipcMain.on('notify:controller', (_, data) => {
  const d = data || {}
  const who = d.player ? `Controller ${d.player}` : 'Controller'
  showHudToast({
    icon: '🎮',
    title: d.connected ? `${who} connected` : `${who} disconnected`,
    body: d.label ? String(d.label) : '',
    accent: d.connected ? '#4ade80' : '#94a3b8',
  })
})

// ── Overlay monitor (Python) ──────────────────────────────────────────────────
function loadOverlayConfig() {
  const root       = path.join(__dirname, '..')
  const configPath = path.join(root, 'config', 'overlays.json')
  try {
    return JSON.parse(fs.readFileSync(configPath, 'utf8'))
  } catch {
    return {}
  }
}

function startOverlayMonitor() {
  if (monitorProcess) return

  const root   = path.join(__dirname, '..')
  const venv   = path.join(root, '.venv', 'bin', 'python')
  const python = fs.existsSync(venv) ? venv : 'python3'
  const script = path.join(root, 'backend', 'services', 'overlay_monitor.py')

  if (!fs.existsSync(script)) return

  monitorProcess = spawn(python, [script], {
    cwd: root,
    stdio: ['pipe', 'pipe', 'ignore'],
  })

  // Parse JSON-lines from monitor stdout
  let buffer = ''
  monitorProcess.stdout.on('data', chunk => {
    buffer += chunk.toString()
    const lines = buffer.split('\n')
    buffer = lines.pop() // keep incomplete line
    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const msg = JSON.parse(line)
        handleMonitorEvent(msg)
      } catch { /* ignore malformed lines */ }
    }
  })

  monitorProcess.on('exit', () => { monitorProcess = null })
}

function stopOverlayMonitor() {
  if (!monitorProcess) return
  try {
    monitorProcess.stdin.write(JSON.stringify({ cmd: 'quit' }) + '\n')
  } catch { /* ignore */ }
  setTimeout(() => {
    if (monitorProcess) { monitorProcess.kill(); monitorProcess = null }
  }, 2000)
}

function handleMonitorEvent(msg) {
  if (DEBUG) console.log('[overlay-monitor]', JSON.stringify(msg))

  switch (msg.event) {
    case 'window:waiting':
      if (overlayWindow) overlayWindow.webContents.send('overlay:waiting', msg)
      if (mainWindow)    mainWindow.webContents.send('overlay:waiting', msg)
      break

    case 'window:ready':
      createOverlayWindow()
      // Hide the main window so the transparent hole shows the emulator directly.
      // If mainWindow stays visible it sits between overlay and emulator, making
      // the hole appear black (showing GameCore's dark background instead).
      if (mainWindow) {
        console.log('[overlay] hiding mainWindow — isVisible:', mainWindow.isVisible())
        mainWindow.hide()
        console.log('[overlay] mainWindow hidden — isVisible now:', mainWindow.isVisible())
      }
      // Wait for the overlay page to finish loading before sending the event,
      // otherwise the React listener isn't mounted yet and the event is lost.
      if (overlayWindow) {
        // The asset travels with the geometry. Without it the overlay page
        // would rebuild the URL from system_id and always draw the system
        // bezel — the per-game resolution would be computed and then thrown
        // away one process boundary before it was used.
        const shown = { ...msg, asset: overlayChoice?.asset ?? null,
                        source: overlayChoice?.source ?? 'declared' }
        overlayWindow.webContents.once('did-finish-load', () => {
          overlayWindow?.webContents.send('overlay:show', shown)
        })
      }
      break

    case 'window:closed':
      destroyOverlayWindow()
      if (mainWindow) {
        mainWindow.show()
        mainWindow.webContents.send('overlay:hide', msg)
      }
      break

    // The emulator drew somewhere other than the hole said it would. Two
    // things happen, and they are deliberately independent: the overlay moves
    // its hole now, so this game is right immediately; and the backend is
    // told, so the next launch starts out right without looking again.
    case 'window:measured':
      if (overlayWindow) {
        overlayWindow.webContents.send('overlay:show', {
          ...msg, rect: msg.measured,
          asset: overlayChoice?.asset ?? null,
          source: overlayChoice?.source ?? 'declared',
        })
      }
      fetch(`${BACKEND_URL}/api/overlays/measured/${encodeURIComponent(msg.system_id)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ announced: msg.announced, measured: msg.measured,
                               window: msg.window }),
        signal: AbortSignal.timeout(4000),
      }).catch(() => { /* a correction not learned is next launch's problem */ })
      break

    case 'error':
      if (DEBUG) console.error('[overlay-monitor] error:', msg.message)
      break
  }
}

// Which bezel this launch resolved to, and where its hole falls. Set just
// before the monitor is told to watch, read again when 'window:ready' comes
// back — the monitor reports geometry and knows nothing about artwork.
let overlayChoice = null

// The backend measures the hole out of the PNG's own alpha channel, so the
// answer follows whatever bezel is actually on this box. Deciding it here
// instead would mean a second PNG decoder in JavaScript and two sets of
// numbers to keep in agreement; `config/overlays.json` is the fallback for a
// system with no PNG at all, and the backend already reads it.
function resolveBezel(system_id, game_key) {
  const q = new URLSearchParams({ rom: game_key || '' })
  return fetch(`${BACKEND_URL}/api/overlays/resolve/${encodeURIComponent(system_id)}?${q}`,
               { signal: AbortSignal.timeout(4000) })
    .then(r => (r.ok ? r.json() : null))
    .catch(() => null)
}

// ── IPC — overlay control (from renderer) ────────────────────────────────────
ipcMain.on('overlay:start', async (_, { system_id, game_key }) => {
  const configs = loadOverlayConfig()
  const cfg     = configs[system_id]
  if (!cfg) return

  // Awaited before the monitor starts, not raced against it: the monitor
  // emits 'window:ready' as soon as the emulator's window appears, and a
  // choice that arrived after that point would draw the previous game's bezel.
  const choice = await resolveBezel(system_id, game_key)

  // A backend that did not answer is not a reason to skip the overlay — the
  // declared geometry is exactly what this code used before there was an
  // endpoint to ask.
  overlayChoice = choice && choice.source !== 'none'
    ? choice
    : { source: 'declared', asset: null, hole: cfg.hole || null }

  startOverlayMonitor()

  // `measure`/`announced` ride along so the monitor knows whether to look at
  // the screen at all, and against which rectangle to report what it sees.
  const watched = overlayChoice.hole
    ? { ...cfg, hole: overlayChoice.hole,
        measure: !!overlayChoice.measure, announced: overlayChoice.announced }
    : cfg
  const cmd = JSON.stringify({ cmd: 'watch', system_id, config: watched }) + '\n'
  try { monitorProcess?.stdin.write(cmd) } catch { /* monitor not ready yet */ }
})

ipcMain.on('overlay:stop', (_, { system_id }) => {
  // Tear the overlay down and bring the UI back FIRST, before anything that
  // depends on the monitor still being alive. This used to `return` when
  // monitorProcess was gone — and by then 'window:ready' had already hidden
  // mainWindow, so the bezel stayed on screen with the interface invisible
  // behind it and no way to get back to it.
  destroyOverlayWindow()
  if (mainWindow) mainWindow.show()
  // Cleared here rather than on the next start: a stale choice surviving a
  // failed launch is the previous game's bezel drawn over the new one.
  overlayChoice = null

  if (!monitorProcess) return
  try {
    monitorProcess.stdin.write(JSON.stringify({ cmd: 'stop', system_id }) + '\n')
  } catch { /* ignore */ }
})

// ── Backend startup ───────────────────────────────────────────────────────────
function backendAlive() {
  return fetch(BACKEND_URL + '/api/sysinfo', { signal: AbortSignal.timeout(1500) })
    .then(() => true)
    .catch(() => false)
}

async function startBackend() {
  if (DEV) return  // dev: backend is started manually

  // In production gamecore-backend.service already runs uvicorn on BACKEND_PORT —
  // spawning a second one just made it crash on EADDRINUSE at every boot.
  // Only spawn when nothing answers (desktop launch without the service).
  if (await backendAlive()) return

  const root   = path.join(__dirname, '..')
  const venv   = path.join(root, '.venv', 'bin', 'python')
  const python = fs.existsSync(venv) ? venv : 'python3'

  backendProcess = spawn(
    python, ['-m', 'uvicorn', 'backend.main:app',
             '--host', '127.0.0.1', '--port', BACKEND_PORT,
             '--log-level', DEBUG ? 'debug' : 'warning'],
    { cwd: root, detached: false, stdio: 'ignore' }
  )

  return new Promise((resolve) => {
    const start = Date.now()
    const check = () => {
      fetch(BACKEND_URL + '/api/sysinfo')
        .then(() => resolve())
        .catch(() => {
          if (Date.now() - start < 10000) setTimeout(check, 300)
          else resolve()
        })
    }
    setTimeout(check, 500)
  })
}

// ── IPC handlers ──────────────────────────────────────────────────────────────
ipcMain.on('system:reboot',   () => exec('sudo systemctl reboot'))
ipcMain.on('system:shutdown', () => exec('sudo systemctl poweroff'))
// The ONLY way out. Settings → Desktop sends this; everything else that closes
// a window is an accident, and window-all-closed below reads this flag to tell
// the two apart.
ipcMain.on('system:quit',     () => { quitting = true; app.quit() })

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  // Everything is served from localhost, so the HTTP cache buys nothing —
  // but a stale cached index.html after an OTA update keeps loading the OLD
  // frontend bundle. Clear it on every start so updates always show up.
  try { await session.defaultSession.clearCache() } catch (_) {}
  await startBackend()
  createWindow()
  startOverlayMonitor()
})

// Electron's boilerplate here is `app.quit()`, which is right for a desktop
// app and wrong for a kiosk: a console does not exit because a window went
// away. It did exactly that — cleanly, with code 0 — so systemd's
// Restart=on-failure never fired, and the box came back only because the
// desktop launcher happened to start it again, whole, splash and all. That is
// the "the splash reappears while I'm on the board" report.
//
// The window lifecycle is driven by game launches (mainWindow.hide() on start,
// the overlay window created and destroyed around it), which is why it struck
// at random and more often when a launch failed.
//
// So: leaving is a decision, taken in Settings → Desktop, and nowhere else.
// Anything else that empties the window list is a fault to recover from —
// rebuild the window rather than take the whole app down with it.
app.on('window-all-closed', () => {
  if (quitting || process.platform === 'darwin') {
    if (quitting) app.quit()
    return
  }
  const now = Date.now()
  rebuilds = rebuilds.filter((t) => now - t < REBUILD_WINDOW)
  if (rebuilds.length >= REBUILD_LIMIT) {
    console.error(`[gamecore] main window closed ${rebuilds.length} times in ` +
                  `${REBUILD_WINDOW / 1000}s — giving up rather than spinning`)
    quitting = true
    app.quit()
    return
  }
  rebuilds.push(now)
  console.warn('[gamecore] all windows closed with no quit request — rebuilding')
  createWindow()
})

// Any real shutdown passes through here first — Settings → Desktop, but also
// the SIGTERM systemd sends on `systemctl stop`. Without it, windows closing
// during teardown would look like the fault above and rebuild a window while
// the app is on its way out.
app.on('before-quit', () => { quitting = true })

app.on('will-quit', () => {
  stopOverlayMonitor()
  if (backendProcess) backendProcess.kill()
})
