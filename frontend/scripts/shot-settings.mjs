/**
 * Render a Shelf settings screen to static HTML, for a side-by-side against the
 * reference capture. Not a test and not shipped — a darkroom.
 *
 * Run from frontend/ so bare imports resolve:
 *   node shot-harness.mjs <out.html> [category]
 *
 * The theme module is loaded for real; only the SDK around it is stubbed, and
 * the stub answers with the SHAPES the endpoints answer with. A screenshot
 * taken from invented shapes would prove the invention, not the screen.
 */
import { JSDOM } from 'jsdom'
import { readFileSync, writeFileSync } from 'fs'
import { resolve } from 'path'

const [, , outPath = 'out.html'] = process.argv
let category = process.argv[3] || 'wifi'

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>',
  { pretendToBeVisual: true, url: 'http://localhost/' })
globalThis.window = dom.window
globalThis.document = dom.window.document
// `navigator` is a getter-only global on modern Node, so it is defined rather
// than assigned. The theme reads getGamepads() off it and would otherwise see
// Node's own navigator, which has none.
Object.defineProperty(globalThis, 'navigator', {
  value: dom.window.navigator, configurable: true, writable: true,
})
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.Element = dom.window.Element
globalThis.Node = dom.window.Node
globalThis.getComputedStyle = dom.window.getComputedStyle
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 16)
globalThis.cancelAnimationFrame = clearTimeout
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const React = (await import('react')).default
const { createRoot } = await import('react-dom/client')
const htmMod = await import('htm')
const htm = htmMod.default

// ── what the box would answer ───────────────────────────────────────────────
const BOX = {
  '/api/settings/wifi/status': {
    connected: true, ssid: 'patrice.5', ip: '192.168.1.34', iface: 'wlp0s20f3',
    gateway: '192.168.1.1', dns: ['9.9.9.9'], mac: 'DC:A6:32:11:8F:04',
    ethernet: { connected: false, iface: '', ip: '' },
  },
  '/api/settings/wifi/networks': [
    { ssid: 'patrice.5', signal: 82, secured: true, connected: true },
    { ssid: 'FreeWifi_Secure', signal: 64, secured: true, connected: false },
    { ssid: 'Neuf_A2C1', signal: 58, secured: true, connected: false },
    { ssid: 'SFR-8842', signal: 41, secured: true, connected: false },
    { ssid: 'Console-Hotspot', signal: 33, secured: false, connected: false },
    { ssid: 'Bbox-19DE', signal: 21, secured: true, connected: false },
  ],
  '/api/settings/wifi/details': [
    { ssid: 'patrice.5', security: 'WPA3', channel: 44, band: '5 GHz', rate: '866 Mb/s' },
    { ssid: 'FreeWifi_Secure', security: 'WPA2', channel: 100, band: '5 GHz', rate: '433 Mb/s' },
    { ssid: 'Neuf_A2C1', security: 'WPA2', channel: 6, band: '2.4 GHz', rate: '144 Mb/s' },
    { ssid: 'SFR-8842', security: 'WPA2', channel: 11, band: '2.4 GHz', rate: '72 Mb/s' },
    { ssid: 'Console-Hotspot', security: 'Open', channel: 36, band: '5 GHz', rate: '200 Mb/s' },
    { ssid: 'Bbox-19DE', security: 'WPA2', channel: 1, band: '2.4 GHz', rate: '54 Mb/s' },
  ],
  '/api/settings/bluetooth/devices': [
    { mac: 'E4:17:D8:2A:9C:03', name: '8BitDo Ultimate 2C', connected: true, paired: true },
    { mac: '5C:BA:11:60:7F:AA', name: 'DualSense Wireless', connected: true, paired: true },
  ],
  '/api/settings/audio/sinks': [
    { id: '49', name: 'Built-in Audio Analog Stereo', default: false },
    { id: '52', name: 'HDMI / DisplayPort', default: true },
  ],
  '/api/settings/audio': { volume: 64, muted: false },
  '/api/settings/bluetooth/scan': { ok: true, seconds: 8, found: [
    { mac: '7C:ED:8D:12:04:B1', name: 'Xbox Wireless Controller', connected: false, paired: false },
    { mac: '38:18:4C:9A:22:77', name: 'WH-1000XM4', connected: false, paired: false },
    { mac: 'C8:3F:26:71:E5:40', name: 'Keyboard K380', connected: false, paired: false },
  ] },
  '/api/standby': { state: 'awake', enabled: true, screensaver_mins: 6, sleep_mins: 16 },
  '/api/storage/volumes': { ok: true, volumes: [
    { name: 'SANDISK Ultra', device: '/dev/sdb1', label: 'SANDISK', uuid: 'x', fstype: 'exfat',
      size: '64 GB', mountpoint: '/run/media/pavic/SANDISK', mounted: true, slug: 'sandisk',
      stable_path: '/home/pavic/GameCore/volumes/sandisk' },
  ] },
  '/api/update/status': { running: false },
  '/api/bios': [
    { id: 'pcsx2', label: 'PlayStation 2', platform: 'ps2', color: '#4f6fd0',
      dir: '/home/pavic/.var/app/net.pcsx2.PCSX2/config/PCSX2/bios', status: 'ok', installed: true,
      files: [{ file: 'ps2-0150e-20001228.bin', path: '/x/ps2.bin', required: true, verified: true,
        expected_md5: 'abc', status: 'ok',
        note: "PlayStation 2 boot ROM. GameCore's PCSX2 configuration names this exact file, so PCSX2 starts with this one or with none." }] },
    { id: 'rpcs3', label: 'PlayStation 3', platform: 'ps3', color: '#2f3f66',
      dir: '/home/pavic/.var/app/net.rpcs3.RPCS3/config/rpcs3/dev_flash/sys/external', status: 'ok', installed: true,
      files: [{ file: 'liblv2.sprx', path: '/x/liblv2.sprx', required: true, verified: false,
        expected_md5: '', status: 'ok',
        note: 'PS3 firmware. Install it from RPCS3 itself, from a PUP you supply — this module is what says the install finished.' }] },
    { id: 'cemu', label: 'Wii U', platform: 'wiiu', color: '#3fae8a',
      dir: '/home/pavic/.var/app/info.cemu.Cemu/data/Cemu', status: 'absent', installed: false,
      files: [{ file: 'keys.txt', path: '/x/keys.txt', required: true, verified: false,
        expected_md5: '', status: 'absent',
        note: 'Wii U title keys, needed to read an encrypted retail dump. A decrypted game runs without it.' }] },
    { id: 'ryujinx', label: 'Nintendo Switch', platform: 'switch', color: '#c62f2f',
      dir: '/home/pavic/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx/system', status: 'ok', installed: true,
      files: [{ file: 'prod.keys', path: '/x/prod.keys', required: true, verified: false,
        expected_md5: '', status: 'ok',
        note: 'Switch console keys. Without them Ryujinx decrypts nothing and stops on a black window.' }] },
  ],
  '/api/catalog': [
    { id: 'xemu', kind: 'emulator', label: 'Xbox', family: 'Microsoft', color: '#3a7d3a', emulatorName: 'xemu', installed: false },
    { id: 'mgba', kind: 'emulator', label: 'Game Boy Advance', family: 'Nintendo', color: '#6ec06e', emulatorName: 'mGBA', installed: true },
    { id: 'dolphin', kind: 'emulator', label: 'GameCube / Wii', family: 'Nintendo', color: '#e08a2e', emulatorName: 'Dolphin', installed: true },
    { id: 'azahar', kind: 'emulator', label: 'Nintendo 3DS', family: 'Nintendo', color: '#c8408a', emulatorName: 'Azahar', installed: true },
    { id: 'melonds', kind: 'emulator', label: 'Nintendo DS', family: 'Nintendo', color: '#2f6fd0', emulatorName: 'melonDS', installed: true },
    { id: 'ryujinx', kind: 'emulator', label: 'Nintendo Switch', family: 'Nintendo', color: '#c62f2f', emulatorName: 'Ryujinx', installed: true },
    { id: 'cemu', kind: 'emulator', label: 'Wii U', family: 'Nintendo', color: '#3fae8a', emulatorName: 'Cemu', installed: false },
    { id: 'pcsx2', kind: 'emulator', label: 'PlayStation 2', family: 'Sony', color: '#4f6fd0', emulatorName: 'PCSX2', installed: true },
    { id: 'rpcs3', kind: 'emulator', label: 'PlayStation 3', family: 'Sony', color: '#2f3f66', emulatorName: 'RPCS3', installed: true },
    { id: 'ppsspp', kind: 'emulator', label: 'PSP', family: 'Sony', color: '#6a6f7a', emulatorName: 'PPSSPP', installed: true },
    { id: 'stremio', kind: 'app', label: 'Stremio', family: 'Applications', color: '#7b5bd0', emulatorName: 'Media library', installed: true },
    { id: 'moonlight', kind: 'app', label: 'Moonlight', family: 'Applications', color: '#3fae8a', emulatorName: 'Game streaming', installed: true },
  ],
  '/api/themes': { sdk_version: 1, active: 'shelf', themes: [
    { id: 'shelf', name: 'Shelf', version: '2.0.0', compatible: true, api: 1,
      description: 'Your library as boxed games on a papered wall' },
    { id: 'summer', name: 'Summer', version: '1.3.0', compatible: true, api: 1,
      description: 'A WebGL ocean that tracks the real sun, under glass panels' },
  ] },
  '/api/sysinfo': {
    ip: '192.168.1.34', storage_used_gb: 218, storage_total_gb: 745, storage_free_gb: 527,
    version: '1.0.160',
    controllers: [{ level: 82, player: 1 }],
    bios: { ok: true, systems: {} },
  },
}
// `<category>@stall` freezes every request, so the shot shows what a page looks
// like while it is still waiting — the state the empty-message bug lived in.
const STALL = category.endsWith('@stall')
if (STALL) category = category.slice(0, -6)
globalThis.fetch = async (input) => {
  const url = String(input)
  if (STALL) return new Promise(() => {})
  const key = Object.keys(BOX).find((k) => url.endsWith(k))
  return {
    ok: !!key, status: key ? 200 : 404, statusText: key ? 'OK' : 'Not Found',
    json: async () => (key ? BOX[key] : {}),
  }
}
dom.window.fetch = globalThis.fetch

// Two pads, the way the Gamepad API reports them.
dom.window.navigator.getGamepads = () => ([
  { index: 0, id: '8BitDo Ultimate 2C', buttons: { length: 17 }, axes: { length: 4 } },
  { index: 1, id: 'DualSense Wireless', buttons: { length: 17 }, axes: { length: 4 } },
])

// ── the SDK, stubbed at the surface the theme actually uses ─────────────────
const html = htm.bind(React.createElement)

// The host's real keyboard, imported rather than stubbed: its whole problem is
// that it draws itself in hardcoded white, which a placeholder cannot show.
const { VirtualKeyboard: KEYBOARD } = await import('../src/components/ui/VirtualKeyboard.tsx')
  .catch(() => ({ VirtualKeyboard: () => html`<div class="cz-kb-stub">keyboard unavailable</div>` }))
const noop = () => () => {}
const api = {
  sysinfo: () => fetch('/api/sysinfo').then((r) => r.json()),
  systems: { get: async () => ({ label: 'GameCore' }) },
  wifi: {
    status: () => fetch('/api/settings/wifi/status').then((r) => r.json()),
    networks: () => fetch('/api/settings/wifi/networks').then((r) => r.json()),
    details: () => fetch('/api/settings/wifi/details').then((r) => r.json()),
    connect: async () => ({ ok: true }),
    disconnect: async () => ({ ok: true }),
  },
  bluetooth: {
    devices: () => fetch('/api/settings/bluetooth/devices').then((r) => r.json()),
    scan: () => fetch('/api/settings/bluetooth/scan').then((r) => r.json()),
    pair: async () => ({ ok: true, message: 'Paired' }),
    connect: async () => ({ ok: true, message: 'Connected' }),
    disconnect: async () => ({ ok: true }),
  },
  standby: {
    get: () => fetch('/api/standby').then((r) => r.json()),
    setConfig: async (c) => c,
  },
  storage: { list: () => fetch('/api/storage/volumes').then((r) => r.json()), unmount: async () => ({ ok: true }) },
  update: { status: () => fetch('/api/update/status').then((r) => r.json()), check: async () => ({}), apply: async () => ({}) },
  controllers: { scanMapping: async () => ({ ok: true }), forgetScan: async () => ({ ok: true }) },
  audio: {
    get: () => fetch('/api/settings/audio').then((r) => r.json()),
    sinks: () => fetch('/api/settings/audio/sinks').then((r) => r.json()),
    setVolume: async () => ({ ok: true }), setSink: async () => ({ ok: true }),
  },
  catalog: {
    list: () => fetch('/api/catalog').then((r) => r.json()),
    busy: async () => ({ busy: false }),
    install: async () => ({}), remove: async () => ({}),
  },
  bios: { list: () => fetch('/api/bios').then((r) => r.json()) },
}
const sdk = {
  ui: {
    html, React,
    useState: React.useState, useEffect: React.useEffect, useRef: React.useRef,
    useMemo: React.useMemo, useCallback: React.useCallback,
  },
  api,
  format: { time: String, date: String },
  themes: { list: () => fetch('/api/themes').then((r) => r.json()) },
  nav: { use: (sel) => sel({ screen: 'home', selectedSystemId: null }) },
  input: { onGp: noop, haptics: { enabled: true }, rumble() {} },
  system: { playSound() {}, onWsEvent: noop, asset: (p) => p,
    sound: { enabled: true, volume: 0.6 } },
  defaults: {
    DefaultSettingsPages: {},
    DefaultKeyboard: KEYBOARD,
  },
}

const THEME = resolve(import.meta.dirname, '../../config/themes/shelf')
const SHARED = resolve(import.meta.dirname, '../../config/themes/_shared/settings')
// Which theme dresses the shot. The screen is shared; the stylesheet and the
// top bar are not, so both come from the same theme or the shot is a lie.
const themeDir = process.env.SHOT_THEME
  ? resolve(import.meta.dirname, `../../config/themes/${process.env.SHOT_THEME}`)
  : THEME
const { createSettings } = await import(`${SHARED}/screen.js`)
const { createTopBar } = await import(`${themeDir}/views/topbar.js`)

const Settings = createSettings(sdk, {}, { TopBar: createTopBar(sdk) })

// The power menu is PowerModal's, not the settings screen's, so it is rendered
// on its own — with the option list the host hands a theme that declares
// `powerOmit: ['scan','forget']`, which is the whole point of the filter.
let Root = Settings
if (category === 'home') {
  // The wall and the bar over it, and nothing else — this shot exists to check
  // one thing: that the top bar is still readable on the new pattern.
  const { createBackground } = await import(`${THEME}/views/background.js`)
  const { NEUTRAL } = await import(`${THEME}/lib/accent.js`)
  const accent = { use: () => NEUTRAL, subscribe: () => () => {} }
  const Background = createBackground(sdk, accent, () => false)
  const TopBar = createTopBar(sdk)
  Root = () => React.createElement(
    'div', { style: { position: 'relative', width: '1920px', height: '1080px' } },
    React.createElement(Background),
    React.createElement(TopBar, { onSettings() {}, onPower() {} }),
  )
} else if (category === 'power') {
  const { createPowerView } = await import(`${SHARED}/power.js`)
  const View = createPowerView(sdk)
  const options = [
    { id: 'shutdown', label: 'Shutdown', busy: 'Shutting down…', icon: '⏻', color: '#b23b3b', desc: 'Power off' },
    { id: 'restart', label: 'Restart', busy: 'Restarting…', icon: '↺', color: '#16897a', desc: 'Reboot the system' },
    { id: 'desktop', label: 'Return to desktop', busy: 'Leaving…', icon: '⌘', color: '#55535C', desc: 'Leave the front end for the system session' },
  ]
  Root = () => React.createElement(View, {
    options, focusIdx: 0, confirmId: null, pendingId: null,
    scanning: false, scanResult: null,
    onFocus() {}, onActivate() {}, onCancel() {},
  })
}

const { act } = await import('react')
const root = createRoot(document.getElementById('root'))
await act(async () => { root.render(React.createElement(Root, { onClose() {} })) })
// Let the eight independent reads land.
await act(async () => { await new Promise((r) => setTimeout(r, 120)) })

if (category === 'wifi-dialog') {
  // Click a secured network that is not the active one: that is the path that
  // raises the password dialog, and clicking it is how a player gets there.
  const row = [...document.querySelectorAll('.gcs-wifi-row')]
    .find((r) => r.textContent.includes('FreeWifi_Secure'))
  if (row) await act(async () => { row.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })) })
  await act(async () => { await new Promise((r) => setTimeout(r, 80)) })
} else if (category !== 'wifi') {
  // Click the rail row for another category, the way a player would.
  const rows = [...document.querySelectorAll('.gcs-set-row')]
  const row = rows.find((r) => r.textContent.toLowerCase().includes(category.toLowerCase()))
  if (row) await act(async () => { row.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })) })
  await act(async () => { await new Promise((r) => setTimeout(r, 80)) })
}

const css = readFileSync(`${themeDir}/theme.css`, 'utf8')
writeFileSync(outPath, `<!doctype html><html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<style>${css}
  html,body{margin:0;padding:0;width:1920px;height:1080px;overflow:hidden}
  .cz-kb-stub{margin-top:18px;padding:26px;border-radius:14px;text-align:center;
    background:rgba(23,23,26,0.05);border:1px dashed rgba(23,23,26,0.25);
    font-family:var(--font-mono);font-size:13px;color:rgba(23,23,26,0.55)}
</style></head><body>${document.getElementById('root').innerHTML}</body></html>`)
console.log(`wrote ${outPath}`)
process.exit(0)
