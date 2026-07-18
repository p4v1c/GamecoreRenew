'use strict'
const { app, BrowserWindow, ipcMain, screen, session } = require('electron')
const { exec, spawn } = require('child_process')
const path = require('path')
const fs   = require('fs')

// Required on Linux X11 for per-pixel transparency in BrowserWindow
app.commandLine.appendSwitch('enable-transparent-visuals')

// Chromium keeps WebAudio suspended until a "user gesture" — and gamepad
// buttons don't count as one (only mouse/keyboard do). On a controller-only
// kiosk the UI sounds would stay silent forever without this.
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required')

const DEBUG = false

const DEV = DEBUG && process.env.ELECTRON_DEV === '1'
const BACKEND_URL = 'http://localhost:8765'
const DEV_URL     = 'http://localhost:5173'

let mainWindow     = null
let backendProcess = null
let overlayWindow  = null
let monitorProcess = null

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

  if (DEV) {
    mainWindow.loadURL(DEV_URL)
  } else {
    mainWindow.loadURL(BACKEND_URL)
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

function showHudToast({ icon = '🎮', title = '', body = '', accent = '#fbbf24' } = {}) {
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
        overlayWindow.webContents.once('did-finish-load', () => {
          overlayWindow?.webContents.send('overlay:show', msg)
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

    case 'error':
      if (DEBUG) console.error('[overlay-monitor] error:', msg.message)
      break
  }
}

// ── IPC — overlay control (from renderer) ────────────────────────────────────
ipcMain.on('overlay:start', (_, { system_id }) => {
  const configs = loadOverlayConfig()
  const cfg     = configs[system_id]
  if (!cfg) return

  startOverlayMonitor()

  const cmd = JSON.stringify({ cmd: 'watch', system_id, config: cfg }) + '\n'
  try { monitorProcess?.stdin.write(cmd) } catch { /* monitor not ready yet */ }
})

ipcMain.on('overlay:stop', (_, { system_id }) => {
  if (!monitorProcess) return
  try {
    monitorProcess.stdin.write(JSON.stringify({ cmd: 'stop', system_id }) + '\n')
  } catch { /* ignore */ }
  destroyOverlayWindow()
})

// ── Backend startup ───────────────────────────────────────────────────────────
function startBackend() {
  if (DEV) return  // dev: backend is started manually

  const root   = path.join(__dirname, '..')
  const venv   = path.join(root, '.venv', 'bin', 'python')
  const python = fs.existsSync(venv) ? venv : 'python3'

  backendProcess = spawn(
    python, ['-m', 'uvicorn', 'backend.main:app',
             '--host', '0.0.0.0', '--port', '8765',
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
ipcMain.on('system:quit',     () => app.quit())

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

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('will-quit', () => {
  stopOverlayMonitor()
  if (backendProcess) backendProcess.kill()
})
