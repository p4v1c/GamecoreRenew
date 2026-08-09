'use strict'
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('gamecore', {
  reboot:   () => ipcRenderer.send('system:reboot'),
  shutdown: () => ipcRenderer.send('system:shutdown'),
  quit:     () => ipcRenderer.send('system:quit'),

  // Overlay control. `game_key` is the ROM filename the launcher recorded —
  // it is what picks the per-game bezel out of a pack, and omitting it is a
  // launch that silently gets the system bezel instead.
  overlayStart: (system_id, game_key) =>
    ipcRenderer.send('overlay:start', { system_id, game_key }),
  overlayStop:  (system_id) => ipcRenderer.send('overlay:stop',  { system_id }),

  // Alert HUD — shown over fullscreen games where the UI is hidden
  batteryToast:    (data) => ipcRenderer.send('notify:battery', data),
  controllerToast: (data) => ipcRenderer.send('notify:controller', data),

  // Overlay events (main → renderer)
  onOverlayShow:    (cb) => ipcRenderer.on('overlay:show',    (_, d) => cb(d)),
  onOverlayHide:    (cb) => ipcRenderer.on('overlay:hide',    (_, d) => cb(d)),
  onOverlayWaiting: (cb) => ipcRenderer.on('overlay:waiting', (_, d) => cb(d)),
})
