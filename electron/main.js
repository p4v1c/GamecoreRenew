'use strict'
const { app, BrowserWindow, ipcMain } = require('electron')
const { exec } = require('child_process')
const path = require('path')

const BACKEND_URL = 'http://localhost:8765'

let mainWindow = null
let backendProcess = null

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1920,
    height: 1080,
    fullscreen: true,
    kiosk: true,
    frame: false,
    autoHideMenuBar: true,
    backgroundColor: '#09090f',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: true,
    },
  })

  mainWindow.loadURL(BACKEND_URL)

  mainWindow.on('closed', () => { mainWindow = null })
}

// ── Backend startup ───────────────────────────────────────────────────────────
function startBackend() {
  const root = path.join(__dirname, '..')
  const venv = path.join(root, '.venv', 'bin', 'python')
  const python = require('fs').existsSync(venv) ? venv : 'python3'

  backendProcess = require('child_process').spawn(
    python, ['-m', 'uvicorn', 'backend.main:app',
             '--host', '0.0.0.0', '--port', '8765', '--log-level', 'warning'],
    { cwd: root, detached: false, stdio: 'ignore' }
  )

  // Wait for backend to be ready (max 10s)
  return new Promise((resolve) => {
    const start = Date.now()
    const check = () => {
      fetch(BACKEND_URL + '/api/sysinfo')
        .then(() => resolve())
        .catch(() => {
          if (Date.now() - start < 10000) setTimeout(check, 300)
          else resolve() // give up, load anyway
        })
    }
    setTimeout(check, 500)
  })
}

// ── IPC handlers ──────────────────────────────────────────────────────────────
ipcMain.on('system:reboot',   () => exec('systemctl reboot'))
ipcMain.on('system:shutdown', () => exec('systemctl poweroff'))
ipcMain.on('system:quit',     () => app.quit())

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  await startBackend()
  createWindow()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('will-quit', () => {
  if (backendProcess) backendProcess.kill()
})
