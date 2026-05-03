'use strict'
const { contextBridge, ipcRenderer } = require('electron')

// Expose only what the renderer needs — no raw Node access
contextBridge.exposeInMainWorld('gamecore', {
  reboot:   () => ipcRenderer.send('system:reboot'),
  shutdown: () => ipcRenderer.send('system:shutdown'),
  quit:     () => ipcRenderer.send('system:quit'),
})
