'use strict'
const { contextBridge, ipcRenderer } = require('electron')

/**
 * The colour the box is booting to — the active theme's, decided by main.js
 * from the manifest on disk and handed over as a window argument.
 *
 * An argument rather than an IPC round trip: the interface's own cover is
 * drawn on its first render, and a value that arrives a round trip later
 * arrives after the frame it was needed for.
 */
const BOOT_BG = (process.argv.find(a => a.startsWith('--gamecore-boot-bg=')) || '')
  .slice('--gamecore-boot-bg='.length) || null

contextBridge.exposeInMainWorld('gamecore', {
  /** `null` outside Electron and on an older shell: callers fall back. */
  bootBackground: BOOT_BG,

  // The host, once it has something worth looking at. One signal, sent once,
  // decided in frontend/src/lib/boot.ts — never by a theme and never by a
  // timer. See the `boot:ready` handler in main.js.
  bootReady: (payload) => ipcRenderer.send('boot:ready', payload || {}),
  reboot:   () => ipcRenderer.send('system:reboot'),
  shutdown: () => ipcRenderer.send('system:shutdown'),
  quit:     () => ipcRenderer.send('system:quit'),

  // Overlay control. `game_key` is the ROM filename the launcher recorded —
  // it is what picks the per-game bezel out of a pack, and omitting it is a
  // launch that silently gets the system bezel instead.
  overlayStart: (system_id, game_key) =>
    ipcRenderer.send('overlay:start', { system_id, game_key }),
  overlayStop:  (system_id) => ipcRenderer.send('overlay:stop',  { system_id }),

  /**
   * Whether a session owns the screen. Told from the same value the input
   * guard reads, so the window and the pad can never disagree.
   *
   * Not part of the overlay: a system with no bezel gets no overlay at all,
   * and that is exactly the case where a resumed game stayed behind the
   * interface — nothing had hidden it.
   */
  sessionScreen: (owned) => ipcRenderer.send('shell:session-screen', { owned: !!owned }),

  // Alert HUD — shown over fullscreen games where the UI is hidden
  batteryToast:    (data) => ipcRenderer.send('notify:battery', data),
  controllerToast: (data) => ipcRenderer.send('notify:controller', data),

  // Overlay events (main → renderer)
  onOverlayShow:    (cb) => ipcRenderer.on('overlay:show',    (_, d) => cb(d)),
  onOverlayHide:    (cb) => ipcRenderer.on('overlay:hide',    (_, d) => cb(d)),
  onOverlayWaiting: (cb) => ipcRenderer.on('overlay:waiting', (_, d) => cb(d)),
})
