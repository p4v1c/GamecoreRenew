'use strict'
const { app, BrowserWindow, ipcMain, screen } = require('electron')
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


/**
 * The colour the box boots to — the active theme's, read from disk.
 *
 * Not a constant, and the reason is measurable: Shelf's boot animation paints
 * `#F4F2ED`, near-white paper. A shell hardcoded to a dark ground therefore
 * flashed dark-to-white at every single boot on the theme the box actually
 * runs — the exact "image blanche entre deux fenêtres" the console boot exists
 * to remove.
 *
 * Read from two files, both on disk, neither needing the backend: the active
 * theme's id, then that theme's manifest. A theme that declares nothing gets
 * the default below, which is what every theme got before this existed.
 *
 * Validated hard, because the value ends up in a window's `backgroundColor`
 * and in the interface's own cover: anything that is not a plain hex colour is
 * refused rather than passed along.
 */
const DEFAULT_BOOT_BG = '#09090f'
const HEX_COLOUR = /^#[0-9a-fA-F]{3,8}$/

function bootBackground() {
  const dataRoot = process.env.GAMECORE_DATA
    || process.env.GAMECORE_PATH
    || path.join(__dirname, '..')
  try {
    const state = JSON.parse(fs.readFileSync(path.join(dataRoot, 'config', 'theme.json'), 'utf8'))
    const id = String(state.active || '')
    // The id names a directory; anything with a separator in it is not an id.
    if (!id || !/^[A-Za-z0-9._-]+$/.test(id)) return DEFAULT_BOOT_BG
    const manifest = JSON.parse(fs.readFileSync(
      path.join(dataRoot, 'config', 'themes', id, 'theme.json'), 'utf8'))
    const declared = manifest && manifest.boot && manifest.boot.background
    if (typeof declared === 'string' && HEX_COLOUR.test(declared.trim())) {
      return declared.trim()
    }
  } catch { /* no theme, no manifest, unreadable JSON — the default is correct */ }
  return DEFAULT_BOOT_BG
}

// ── Main window ───────────────────────────────────────────────────────────────
function createWindow() {
  const bootBg = bootBackground()
  mainWindow = new BrowserWindow({
    width: 1920,
    height: 1080,
    fullscreen: true,
    // Presented on `ready-to-show`, never before: a window shown while its
    // first document is still empty is a white rectangle over the desktop.
    show: false,
    kiosk: !DEBUG && !DEV,
    frame: false,
    autoHideMenuBar: true,
    // Painted before any document exists, and again in the frame between the
    // boot screen and the interface. `boot/boot.html` is transparent so this is
    // the only place the boot colour is decided.
    backgroundColor: bootBg,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: true,
      // Handed to the preload as an argument rather than fetched over IPC: the
      // interface's own cover is drawn on its very first render, and a value
      // that arrives one round trip later is a value that arrives after the
      // frame it was needed for.
      additionalArguments: [`--gamecore-boot-bg=${bootBg}`],
      // This window is the WebSocket bridge for battery alerts even while
      // buried under an emulator or hidden behind a bezel overlay — never
      // let Chromium throttle it in the background.
      backgroundThrottling: false,
    },
  })

  // The local boot screen, from disk, before anything is waited for.
  //
  // This window used to be created only after the backend answered, so what
  // covered the television during that wait was the desktop: wallpaper, panel,
  // and whatever the player had left open. Now the window exists first and the
  // interface is loaded INTO it, which also means there is no second window to
  // stack, focus or cross-fade — the two things a compositor is free to get
  // wrong.
  mainWindow.loadFile(path.join(__dirname, 'boot', 'boot.html'))

  // Shown when it has something to show. Without this, Electron presents the
  // window as soon as it exists and the first frame is white — a white flash
  // on a dark boot is more noticeable than the desktop it replaced.
  mainWindow.once('ready-to-show', () => { mainWindow?.show() })

  // A renderer that dies takes the interface with it, and what is left is a
  // window showing the last frame it painted — a console that looks frozen
  // rather than broken. Put the boot screen back and start the sequence over:
  // the backend is asked again, and `boot:ready` decides again.
  //
  // Bounded by the same rebuild budget the window itself uses, so a renderer
  // that cannot survive its first frame stops rather than spinning.
  mainWindow.webContents.on('render-process-gone', (_e, details) => {
    if (quitting) return
    console.error('[boot] the renderer is gone:', details.reason)
    rebuilds = rebuilds.filter(t => Date.now() - t < REBUILD_WINDOW)
    if (rebuilds.length >= REBUILD_LIMIT) {
      console.error('[boot] too many renderer failures — stopping, systemd will decide')
      app.quit()
      return
    }
    rebuilds.push(Date.now())
    restartBoot()
  })

  if (DEBUG) mainWindow.webContents.openDevTools({ mode: 'detach' })

  mainWindow.on('closed', () => { mainWindow = null })
}

/**
 * Hand the window over to the interface.
 *
 * A navigation inside the same window rather than a second window: the frame
 * between two documents is painted with the window's own `backgroundColor`,
 * which is the same ground the boot screen uses, so the handover is a change
 * of content on an unchanged colour. Two windows would have been a change of
 * WINDOW, and which one the compositor draws on top — and which one has the
 * pad's focus — is not something this code gets to decide.
 *
 * What the player then sees is the theme's own boot animation, which holds its
 * last frame until the interface is ready (SDK 4). The local screen above is
 * deliberately still, so the sequence is one animation, not two.
 */
/**
 * Start the boot again, in the same window.
 *
 * A new generation, so anything still waiting for the previous one — a poll
 * against `/api/ready`, a `boot:ready` from a renderer that has since died —
 * finds its number stale and decides nothing.
 */
async function restartBoot() {
  if (!mainWindow) return
  const generation = ++bootGeneration
  setBootState(BOOT.STARTING)
  mainWindow.loadFile(path.join(__dirname, 'boot', 'boot.html'))
  const up = await waitForBackend(generation)
  if (!up || generation !== bootGeneration) return
  presentApp()
}

function presentApp() {
  if (!mainWindow) return
  setBootState(BOOT.LOADING_UI)
  mainWindow.loadURL(DEV ? DEV_URL : BACKEND_URL)
}

// ── Overlay window ────────────────────────────────────────────────────────────
/**
 * The screen the game is on, in the units BrowserWindow speaks.
 *
 * The bezel was pinned to (0, 0) 1920×1080 while the main window is a genuine
 * fullscreen one. On anything but a 1080p single-screen box that is a bezel
 * covering a quarter of the picture, or sitting on the wrong output — and the
 * distinction that matters is logical against physical: a 4K panel scaled to
 * 200 % reports 1920×1080 of LOGICAL space, which is what `bounds` gives and
 * what this window has to be measured in.
 *
 * `getDisplayMatching` because the game follows the interface, and the
 * interface is where the player put it. Everything here is defensive: a screen
 * API that answers nothing must cost the size of the bezel, never the launch.
 */
function overlayBounds() {
  const fallback = { x: 0, y: 0, width: 1920, height: 1080 }
  try {
    const display = (mainWindow && typeof screen.getDisplayMatching === 'function')
      ? screen.getDisplayMatching(mainWindow.getBounds())
      : screen.getPrimaryDisplay()
    const b = display?.bounds || screen.getPrimaryDisplay()?.bounds
    if (!b || !b.width || !b.height) return fallback
    return { x: b.x || 0, y: b.y || 0, width: b.width, height: b.height }
  } catch {
    return fallback
  }
}

function createOverlayWindow() {
  if (overlayWindow) return

  const at = overlayBounds()
  overlayWindow = new BrowserWindow({
    x: at.x,
    y: at.y,
    width: at.width,
    height: at.height,
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

  // Systems this pad was NOT configured for. A pad can be recognised and still
  // be left out of one emulator, and until this branch existed that arrived as
  // the green "connected" toast — so the one console that ignored the pad was
  // the one thing the player was never told about.
  //
  // Same provenance rule as everything else reaching showHudToast: these are
  // catalogue labels relayed by the renderer, so they are text to escape and
  // never markup. Capped because the HUD is a fixed 440x100 window.
  const missing = Array.isArray(d.unconfigured)
    ? d.unconfigured.filter(s => typeof s === 'string').slice(0, 3)
    : []

  // Autoconfig is off, so this pad got nothing anywhere. First, and it names no
  // systems: listing nine of them truncated to three would read as a fault in
  // three consoles instead of one switch somebody flicked. This is also the one
  // moment the player can be told at all — they are in a game, the app window
  // is buried under the emulator, and the pad in their hands does not work.
  if (d.connected && Array.isArray(d.autoconfigOff) && d.autoconfigOff.length > 0) {
    showHudToast({
      icon: '🎮',
      title: `${who} was not configured`,
      body: 'Automatic controller setup is off (Settings → Controllers).',
      accent: '#fbbf24',
    })
    return
  }

  if (d.connected && missing.length > 0) {
    showHudToast({
      icon: '⚠️',
      title: `${who} is not set up for ${missing.join(', ')}`,
      body: `It works elsewhere — ${missing.length === 1 ? 'that system' : 'those systems'} will not respond to it.`,
      accent: '#fbbf24',
    })
    return
  }

  showHudToast({
    icon: '🎮',
    title: d.connected ? `${who} connected` : `${who} disconnected`,
    body: d.label ? String(d.label) : '',
    accent: d.connected ? '#4ade80' : '#94a3b8',
  })
})

// ── Overlay monitor (Python) ──────────────────────────────────────────────────
//
// `config/overlays.json` is the player's — `config/` is excluded from the OTA
// rsync for exactly that reason — so it is read from the DATA root, not from
// the install this file happens to live in. The two are one directory on every
// box installed so far, which is what the fallback preserves; once the data
// has moved, reading it from `__dirname/..` would read the abandoned copy: the
// backend (services/paths.py) and this process would then hold two different
// overlays.json, identical on the day of the move and drifting apart from the
// first edit, with a launch resolving its window from one and its hole from
// the other. The unit passes GAMECORE_DATA to the UI for this line.
function loadOverlayConfig() {
  const root       = process.env.GAMECORE_DATA || path.join(__dirname, '..')
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

// Send to the overlay page, loaded or not.
//
// `once('did-finish-load')` on its own loses the event whenever the page has
// ALREADY finished loading — and that is not a rare case:
//
//   · `createOverlayWindow()` returns early when a window is already there, so
//     any window a previous launch left behind is reused fully loaded;
//   · an emulator that recreates its window makes the monitor emit a second
//     `window:ready`, and the listener attached then never fires either.
//
// The failure is silent and total: the `window:ready` branch still runs, still
// hides the main window, still logs — and no bezel is ever drawn. Waiting only
// when there is actually something to wait for removes the whole class.
function sendToOverlay(channel, payload) {
  if (!overlayWindow) return
  const wc = overlayWindow.webContents
  if (wc.isLoading()) {
    wc.once('did-finish-load', () => overlayWindow?.webContents.send(channel, payload))
  } else {
    wc.send(channel, payload)
  }
}

/**
 * The coordinate space the hole is measured in.
 *
 * `window_rect` is the rectangle the monitor forces the emulator into, and the
 * backend places the hole inside it — so the two are in the same units, and
 * neither is in the units of an overlay window that now follows the screen.
 * Handing this along lets the page speak in fractions instead of pixels.
 */
function overlaySpace(system_id) {
  const rect = loadOverlayConfig()[system_id]?.window_rect
  return (rect && rect.w && rect.h) ? { w: rect.w, h: rect.h } : { w: 1920, h: 1080 }
}

function handleMonitorEvent(msg) {
  if (DEBUG) console.log('[overlay-monitor]', JSON.stringify(msg))

  // A report about a system nobody is watching any more. The monitor is told
  // to stop, but a message already on its way through the pipe still arrives,
  // and acting on it would hide the interface behind a bezel for a game that
  // has ended. `error` carries no system and is always worth reading.
  if (msg.system_id && overlayWatching && msg.system_id !== overlayWatching) return

  switch (msg.event) {
    case 'window:waiting':
      sendToOverlay('overlay:waiting', msg)
      if (mainWindow) mainWindow.webContents.send('overlay:waiting', msg)
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
      if (overlayWindow) {
        // The asset travels with the geometry. Without it the overlay page
        // would rebuild the URL from system_id and always draw the system
        // bezel — the per-game resolution would be computed and then thrown
        // away one process boundary before it was used.
        //
        // `space` is the rectangle the hole's numbers are expressed in — the
        // window the monitor forces the emulator into. The overlay page stops
        // being able to assume 1920x1080 the moment its own window follows the
        // screen, and it draws the fallback bars from the two together.
        const shown = { ...msg, asset: overlayChoice?.asset ?? null,
                        source: overlayChoice?.source ?? 'declared',
                        space: overlaySpace(msg.system_id) }
        // Said out loud, next to the "hiding mainWindow" line above: those two
        // used to be able to disagree — the window hidden, the bezel never
        // sent — and the log gave no way to tell which half had happened.
        console.log('[overlay] show:', shown.source, shown.asset ?? '(aucun bezel)',
                    'chargement en cours:', overlayWindow.webContents.isLoading())
        sendToOverlay('overlay:show', shown)
      }
      break

    case 'window:closed':
      destroyOverlayWindow()
      overlayWatching = null
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
      sendToOverlay('overlay:show', {
        ...msg, rect: msg.measured,
        asset: overlayChoice?.asset ?? null,
        source: overlayChoice?.source ?? 'declared',
        space: overlaySpace(msg.system_id),
      })
      fetch(`${BACKEND_URL}/api/overlays/measured/${encodeURIComponent(msg.system_id)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // `console` comes from the resolve answer, not from the monitor: the
        // monitor is handed a window id and reports geometry, and it has no
        // way to know which of a pack's consoles this ROM was. Without it the
        // correction lands under the pack's shared key and one console's
        // measurement is applied to all of them — which is the whole reason
        // the level exists.
        body: JSON.stringify({ announced: msg.announced, measured: msg.measured,
                               window: msg.window,
                               console: overlayChoice?.console ?? null }),
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

/**
 * Which overlay run is current, and what it is watching.
 *
 * `overlay:start` awaits the backend before it tells the monitor anything, and
 * a game can be gone by the time that answer arrives: press ✕, the emulator
 * fails to start, `overlay:stop` tears the overlay down — and then the resolve
 * came back and the old start carried on, sending `watch` for a game that is
 * no longer running. The monitor then reported on whatever window it found,
 * and the next launch inherited the argument.
 *
 * The number is taken before the await and compared after it. `overlayWatching`
 * is the same guard one level further out: a report about a system nobody is
 * watching any more decides nothing.
 */
let overlayRun = 0
let overlayWatching = null
let overlayResolveAbort = null

// The backend measures the hole out of the PNG's own alpha channel, so the
// answer follows whatever bezel is actually on this box. Deciding it here
// instead would mean a second PNG decoder in JavaScript and two sets of
// numbers to keep in agreement; `config/overlays.json` is the fallback for a
// system with no PNG at all, and the backend already reads it.
function resolveBezel(system_id, game_key, signal) {
  const q = new URLSearchParams({ rom: game_key || '' })
  return fetch(`${BACKEND_URL}/api/overlays/resolve/${encodeURIComponent(system_id)}?${q}`,
               { signal: signal || AbortSignal.timeout(4000) })
    .then(r => (r.ok ? r.json() : null))
    .catch(() => null)
}

// ── IPC — overlay control (from renderer) ────────────────────────────────────
ipcMain.on('overlay:start', async (_, { system_id, game_key }) => {
  const configs = loadOverlayConfig()
  const cfg     = configs[system_id]
  if (!cfg) return

  // Claimed before the first await. Anything that ends this run — a stop, or
  // another launch — takes the next number, and this one then knows it is over.
  const run = ++overlayRun
  const ctl = (typeof AbortController === 'function') ? new AbortController() : null
  overlayResolveAbort = ctl
  const deadline = ctl ? setTimeout(() => ctl.abort(), 4000) : null

  // Awaited before the monitor starts, not raced against it: the monitor
  // emits 'window:ready' as soon as the emulator's window appears, and a
  // choice that arrived after that point would draw the previous game's bezel.
  const choice = await resolveBezel(system_id, game_key, ctl?.signal)
  if (deadline) clearTimeout(deadline)
  if (overlayResolveAbort === ctl) overlayResolveAbort = null

  // The game this was resolved for is not the game the box is on any more.
  // Nothing may be sent: `watch` here is the monitor looking at the next
  // player's window on the last player's behalf.
  if (run !== overlayRun) return

  // A backend that did not answer is not a reason to skip the overlay — the
  // declared geometry is exactly what this code used before there was an
  // endpoint to ask.
  overlayChoice = choice && choice.source !== 'none'
    ? choice
    : { source: 'declared', asset: null, hole: cfg.hole || null }
  overlayWatching = system_id

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
  // Ends the run, including one still waiting on the backend: it will find its
  // number stale and send nothing. The request itself is dropped too — no
  // point holding a socket open for an answer that has nowhere to go.
  overlayRun += 1
  overlayWatching = null
  try { overlayResolveAbort?.abort() } catch { /* already settled */ }
  overlayResolveAbort = null

  if (!monitorProcess) return
  try {
    monitorProcess.stdin.write(JSON.stringify({ cmd: 'stop', system_id }) + '\n')
  } catch { /* ignore */ }
})

// ── Backend startup ───────────────────────────────────────────────────────────
/**
 * Is GameCore usable — not "is something listening".
 *
 * `/api/ready` answers 200 only once the backend's required startup is done,
 * and 503 with the outstanding step until then. This used to ask
 * `/api/sysinfo` and treat ANY response as success: an endpoint that opens a
 * UDP socket towards 8.8.8.8 to find the box's address, walks the disk, reads
 * the controller batteries and lists the BIOS files — polled, on the boot
 * path, to answer a question it was never written for. It also answered
 * perfectly well while the backend was still opening its database, so "alive"
 * arrived several seconds before "usable".
 */
function backendReady() {
  return fetch(BACKEND_URL + '/api/ready', { signal: AbortSignal.timeout(1500) })
    .then(r => (r.ok ? r.json() : null))
    .then(body => !!(body && body.ready))
    .catch(() => false)
}

/**
 * Who owns the backend process.
 *
 * On an installed box, systemd does — `gamecore-backend.service`, with its own
 * restart policy, its own environment and its own journal. Electron spawning a
 * second uvicorn on the same port produced an EADDRINUSE crash loop next to a
 * working backend, and the guard against it was a race: "nothing answered in
 * the last 1.5 s" is true of a backend that is merely still starting.
 *
 * systemd sets INVOCATION_ID in every service it runs, and start-ui.sh is the
 * unit's ExecStart, so Electron inherits it. That is the signal — no installer
 * change, and it cannot drift out of sync with reality. GAMECORE_MANAGED
 * overrides it either way, for a sandbox or a test.
 */
function backendIsManaged() {
  const explicit = process.env.GAMECORE_MANAGED
  if (explicit === '1') return true
  if (explicit === '0') return false
  return !!process.env.INVOCATION_ID
}

async function startBackend() {
  if (DEV) return  // dev: backend is started manually
  if (await backendReady()) return

  // Managed: wait for it, never compete with it. A backend that does not come
  // up is a fault to report — see waitForBackend and the RECOVERING state —
  // not a reason to start a second one.
  if (backendIsManaged()) return

  const root   = path.join(__dirname, '..')
  const venv   = path.join(root, '.venv', 'bin', 'python')
  const python = fs.existsSync(venv) ? venv : 'python3'

  console.log('[boot] no managed backend — starting one from', root)
  backendProcess = spawn(
    python, ['-m', 'uvicorn', 'backend.main:app',
             '--host', '127.0.0.1', '--port', BACKEND_PORT,
             '--log-level', DEBUG ? 'debug' : 'warning'],
    { cwd: root, detached: false, stdio: 'ignore' }
  )
}

// ── The boot, as a state machine ─────────────────────────────────────────────
//
// STARTING → WAITING_BACKEND → LOADING_UI → PRESENTABLE → RUNNING, plus
// RECOVERING when something has gone wrong for long enough to say so.
//
// The rule the whole of this file now follows: **no timer promotes anything**.
// Each transition is a fact — the backend answered `/api/ready`, the renderer
// said `boot:ready`. Durations appear in exactly one role, bounding a failure
// so it can be reported rather than waited on for ever.
const BOOT = {
  STARTING: 'STARTING',
  WAITING_BACKEND: 'WAITING_BACKEND',
  LOADING_UI: 'LOADING_UI',
  PRESENTABLE: 'PRESENTABLE',
  RUNNING: 'RUNNING',
  RECOVERING: 'RECOVERING',
}
let bootState = BOOT.STARTING
// Which boot this is. A window reloaded, or a backend restarted underneath a
// running shell, starts another one — and the answers of the previous one must
// not decide anything for it.
let bootGeneration = 0
const bootStartedAt = Date.now()

function setBootState(next) {
  if (bootState === next) return
  bootState = next
  console.log(`[boot] ${next} (+${Date.now() - bootStartedAt}ms)`)
}

/** How long before a backend that is not answering stops being "slow". */
const BACKEND_PATIENCE_MS = 20000
/** Between two polls. Short enough not to add to the boot, long enough not to
 *  be a load of its own on the machine it is measuring. */
const BACKEND_POLL_MS = 250

/**
 * Wait for the backend, for as long as it takes.
 *
 * There is deliberately no deadline that gives up and carries on: carrying on
 * means showing a home screen built from nothing, which is the one outcome
 * this whole step exists to prevent. `BACKEND_PATIENCE_MS` does not end the
 * wait — it ends the SILENCE, moving the boot into RECOVERING so the shell can
 * say what is wrong. The polling then slows down rather than stopping.
 */
async function waitForBackend(generation) {
  setBootState(BOOT.WAITING_BACKEND)
  let slow = false
  for (;;) {
    if (generation !== bootGeneration) return false
    if (await backendReady()) {
      if (slow) console.log('[boot] the backend answered after all')
      return true
    }
    if (!slow && Date.now() - bootStartedAt > BACKEND_PATIENCE_MS) {
      slow = true
      setBootState(BOOT.RECOVERING)
      console.warn('[boot] the backend is not answering /api/ready — still waiting')
    }
    await new Promise(r => setTimeout(r, slow ? BACKEND_POLL_MS * 8 : BACKEND_POLL_MS))
  }
}

// ── IPC handlers ──────────────────────────────────────────────────────────────
//
// The renderer saying it has something worth looking at: the theme resolved or
// its fallback took over, the home data settled, the input bindings are armed
// and the first view has been painted. Decided in the host — see
// frontend/src/lib/boot.ts — because a condition each theme defined for itself
// would be a different condition per theme, and one of them would be a timer.
ipcMain.on('boot:ready', (_, payload) => {
  if (bootState === BOOT.RUNNING) return
  console.log('[boot] the interface is ready',
              payload && payload.steps ? JSON.stringify(payload.steps) : '')
  setBootState(BOOT.PRESENTABLE)
  setBootState(BOOT.RUNNING)
})

ipcMain.on('system:reboot',   () => exec('sudo systemctl reboot'))
ipcMain.on('system:shutdown', () => exec('sudo systemctl poweroff'))

/**
 * The ONLY way out — and in the console session, leaving is a change of
 * session rather than the end of a program.
 *
 * Quitting used to be enough: GameCore was drawn over the machine's desktop,
 * so closing it revealed the desktop that was already there. There is no
 * desktop behind it any more. Quitting on its own would end the session, SDDM
 * would auto-log straight back in, and the player would watch GameCore start
 * again — which reads as "the button does nothing", pressed harder.
 *
 * So the auto-login is pointed at the desktop FIRST, and only then does the
 * session end. `gamecore-session-select` is the one command the sudoers rule
 * names, with exactly this argument; if it is not there — an un-migrated box,
 * where GameCore really is drawn over a desktop — quitting alone is still
 * exactly right, which is why a failure here does not stop the exit.
 *
 * Everything else that closes a window is an accident, and window-all-closed
 * below reads `quitting` to tell the two apart.
 */
/**
 * Are we the console session, or a window on somebody's desktop?
 *
 * Asked of three variables and case-insensitively, because the session sets
 * them from three different places and they do not agree:
 *
 *     DESKTOP_SESSION=gamecore        the .desktop file's NAME
 *     XDG_SESSION_DESKTOP=GameCore    its DesktopNames= field
 *     XDG_CURRENT_DESKTOP=GameCore    idem, and a colon-list by specification
 *
 * This read `XDG_SESSION_DESKTOP !== 'gamecore'` and nothing else, so on the
 * real box every "Mode bureau" took the early exit: the app quit without ever
 * handing the auto-login back, SDDM's Relogin brought the console straight up
 * again, and from the sofa it looked like the button flashed the screen black
 * and did nothing. One capital letter, in a value we do not own.
 */
function inConsoleSession() {
  return ['DESKTOP_SESSION', 'XDG_SESSION_DESKTOP', 'XDG_CURRENT_DESKTOP']
    .some(name => (process.env[name] || '').split(':')
      .some(word => word.trim().toLowerCase() === 'gamecore'))
}

/**
 * Ask the session to hand the box back to the desktop, and get out of the way.
 *
 * This used to run `sudo gamecore-session-select desktop` here and quit in the
 * callback. On the reference box that call reached sudo every single time —
 * the journal has all five invocations, each exiting 0 in about 30 ms — and
 * the auto-login file was never touched. The same command, run by hand, from a
 * systemd user unit, and from this service's own working directory, wrote it
 * every time. The only thing the failing runs had in common is that they ran
 * inside `gamecore-ui.service`, whose cgroup systemd tears down as soon as
 * this process exits, which is the very next thing that happens.
 *
 * So the privileged part moved to where nothing is racing it: the session
 * script's teardown, which runs in the session's own process after the units
 * are stopped. All that is left here is to say what the player asked for.
 * `install/bin/gamecore-session` reads this file and removes it; a marker left
 * behind by a session that never tore down is cleared at the next login.
 */
function askSessionForDesktop() {
  const runtime = process.env.XDG_RUNTIME_DIR
  if (!runtime) return false
  try {
    const dir = path.join(runtime, 'gamecore')
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 })
    fs.writeFileSync(path.join(dir, 'leave-to-desktop'), `${new Date().toISOString()}\n`)
    return true
  } catch (err) {
    console.warn('[session] could not ask the session to leave:', err.message)
    return false
  }
}

/**
 * The way out for a box whose session script predates the marker above.
 *
 * Kept only for that case: an installation updates its shell and its session
 * script together, but a box can be running an old session from a login that
 * happened before the update. Best effort, and its failure is not fatal — the
 * next login is GameCore again, which is recoverable from a terminal.
 */
function handBackToDesktop(done) {
  const SELECT = '/usr/local/bin/gamecore-session-select'
  let left = false
  const leave = () => { if (!left) { left = true; done() } }
  setTimeout(leave, 10_000).unref?.()
  exec(`sudo -n ${SELECT} desktop --restart-dm`, (err, stdout, stderr) => {
    if (err) console.warn('[session] the fallback switch failed:', err.message, stderr || '')
    else console.log('[session] fallback switch:', String(stdout).trim())
    leave()
  })
}

ipcMain.on('system:quit', () => {
  quitting = true
  if (!inConsoleSession()) { app.quit(); return }
  // The session does the switch on its way out. Quitting is what starts it.
  if (askSessionForDesktop()) { app.quit(); return }
  handBackToDesktop(() => app.quit())
})

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  // There used to be a `session.defaultSession.clearCache()` here, on the
  // reasoning that a localhost cache buys nothing while a stale index.html
  // after an OTA pins the OLD frontend bundle. The second half was right; the
  // first was not. The cache holds the library's cover art, and wiping it on
  // every start meant the box re-downloaded and re-decoded 47 MB of it on
  // every single boot — measured here, 89 files, and the decode is the part
  // the player waits on.
  //
  // What replaces it is a rule instead of a hammer (backend/services/http_cache.py):
  //
  //   · index.html          no-store    — never kept, so it can never pin
  //   · assets/<name>-<hash>.<ext>      immutable — a new build is a new URL
  //   · covers, media, logos            no-cache — kept, revalidated, 304
  //
  // The bundle is immutable BY CONSTRUCTION: Vite names it by content hash, so
  // an old file is unreachable rather than merely unused. The only unhashed
  // file that decides which code runs is index.html, and it is the one file
  // the browser is now forbidden to store. That is why this may go.
  //
  // If an update ever fails to show up on the first launch again, this comment
  // is the place to start — but put the header back, not the wipe.
  const generation = ++bootGeneration
  // The screen is covered first, and everything else happens behind it. This
  // is the whole of the visible change: the order used to be "wait, then show
  // something", and the wait is exactly when there was nothing to see.
  createWindow()
  startOverlayMonitor()

  await startBackend()
  const up = await waitForBackend(generation)
  if (!up || generation !== bootGeneration) return
  presentApp()

  // A television that changes mode, or an output plugged in mid-session, moves
  // the ground under a window that was placed by hand. Registered here and not
  // at module scope: the screen module cannot be talked to before the app is
  // ready. Nothing here is fatal — an Electron whose `screen` cannot be
  // subscribed to keeps the bezel the size it was given.
  try {
    const refit = () => {
      if (!overlayWindow) return
      try { overlayWindow.setBounds(overlayBounds()) } catch { /* window going away */ }
    }
    screen.on?.('display-metrics-changed', refit)
    screen.on?.('display-added', refit)
    screen.on?.('display-removed', refit)
  } catch { /* no screen module to listen to */ }
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

/**
 * `systemctl stop` has to stop this, and it did not.
 *
 * Every update ends with `gamecore-restart.service` stopping the UI unit.
 * SIGTERM reached the shell and the shell stayed up: systemd waited its full
 * ninety seconds and then SIGKILLed both processes. Measured on the reference
 * box, 08:34:04 → 08:35:35, one minute and forty-five seconds of interface
 * left on the television with its backend already stopped underneath it — long
 * enough to draw whatever a front end draws when nothing answers.
 *
 * The cause is the guard above this: `window-all-closed` cannot tell a
 * teardown from a crash, so windows closing during a shutdown that never went
 * through `before-quit` look like a fault, and it rebuilds one. The app then
 * has a window again and no reason to leave.
 *
 * So the signal says what it means. `quitting` first, `app.quit()` second —
 * in that order, because the quit closes the windows and the flag is what
 * `window-all-closed` reads to let them stay closed.
 */
for (const signal of ['SIGTERM', 'SIGINT', 'SIGHUP']) {
  process.on(signal, () => {
    console.log(`[gamecore] ${signal} — leaving`)
    quitting = true
    app.quit()
  })
}

app.on('will-quit', () => {
  stopOverlayMonitor()
  if (backendProcess) backendProcess.kill()
})
