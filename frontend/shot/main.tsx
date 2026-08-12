/**
 * A darkroom for the DEFAULT UI.
 *
 * The theme screens can be rendered with a stubbed SDK, but the built-in UI is
 * ordinary React with its own imports — it needs the real bundler. So this is a
 * second vite entry that mounts one host surface with the box's answers faked,
 * built to static files a headless browser can open.
 *
 * Not shipped: `vite.shot.config.mts` is the only thing that builds it, and
 * `npm run build` never sees this folder.
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import SettingsModal from '../src/components/modals/SettingsModal'
import PowerModal from '../src/components/modals/PowerModal'
import { WifiPage } from '../src/components/modals/settings/WifiPage'
import SettingsScreen from '../src/components/modals/SettingsScreen'
import { Overlay } from '../src/components/ui'
import { VirtualKeyboard } from '../src/components/ui/VirtualKeyboard'

const BOX: Record<string, unknown> = {
  '/api/settings/wifi/status': {
    connected: true, ssid: 'patrice.5', ip: '192.168.1.34', iface: 'w0',
    gateway: '192.168.1.1', dns: ['9.9.9.9'], mac: 'DC:A6:32:11:8F:04',
    ethernet: { connected: false, iface: '', ip: '' },
  },
  '/api/settings/wifi/networks': [
    { ssid: 'patrice.5', signal: 82, secured: true, connected: true },
    { ssid: 'FreeWifi_Secure', signal: 64, secured: true, connected: false },
    { ssid: 'Neuf_A2C1', signal: 41, secured: true, connected: false },
  ],
  '/api/settings/wifi/details': [
    { ssid: 'patrice.5', security: 'WPA3', channel: 44, band: '5 GHz', rate: '866 Mb/s' },
  ],
  '/api/settings/bluetooth/devices': [
    { mac: 'a', name: '8BitDo Ultimate 2C', connected: true, paired: true },
    { mac: 'b', name: 'DualSense Wireless', connected: true, paired: true },
  ],
  '/api/settings/audio/sinks': [{ id: '1', name: 'HDMI / DisplayPort', default: true }],
  '/api/settings/audio': { volume: 64, muted: false },
  '/api/storage/volumes': { ok: true, volumes: [{ device: '/dev/sdb1', label: 'SANDISK' }] },
  '/api/standby': { enabled: true, screensaver_mins: 6, sleep_mins: 16, state: 'awake' },
  '/api/catalog': Array.from({ length: 18 }, (_, i) => ({ id: `p${i}`, installed: i < 15 })),
  '/api/bios': Array.from({ length: 5 }, (_, i) => ({ id: `b${i}`, status: 'ok' })),
  '/api/sysinfo': { version: '1.0.172', controllers: [], bios: { ok: true, systems: {} } },
  '/api/themes': {
    sdk_version: 1, active: null,
    themes: [{ id: 'shelf', name: 'Shelf', version: '2.9.0', compatible: true }],
  },
}
window.fetch = (async (input: RequestInfo | URL) => {
  const url = String(input)
  const hit = Object.keys(BOX).find(k => url.endsWith(k))
  if (!hit) return { ok: true, status: 200, statusText: 'OK', json: async () => ({}) } as Response
  return { ok: true, status: 200, statusText: 'OK', json: async () => BOX[hit] } as Response
}) as typeof fetch

const params = new URLSearchParams(location.search)
const which = params.get('s') ?? 'settings'

/**
 * `?theme=shelf` drops that theme's real stylesheet over the page.
 *
 * The game search keyboard is drawn by the HOST inside the host's overlay, so
 * what it looks like under a theme is decided entirely by tokens that
 * stylesheet sets. Screenshotting it without the stylesheet would be
 * screenshotting the thing this change is about not being the case any more.
 * `shot.sh` copies the two files in beside the bundle.
 */
const themeId = params.get('theme')
if (themeId) {
  const link = document.createElement('link')
  link.rel = 'stylesheet'
  link.href = `/theme-${themeId}.css`
  document.head.appendChild(link)
}

const Root = () =>
  which === 'rail' ? <SettingsScreen onClose={() => {}} />
  : which === 'power' ? <PowerModal onClose={() => {}} />
  : which === 'wifi' ? <WifiPage onClose={() => {}} onBack={() => {}} />
  : which === 'search' ? (
      <Overlay onClose={() => {}}>
        <VirtualKeyboard className="gc-search-kb" title="Search games"
          placeholder="search a game…" onConfirm={() => {}} onCancel={() => {}} />
      </Overlay>
    )
  : <SettingsModal onClose={() => {}} />

ReactDOM.createRoot(document.getElementById('root')!).render(<Root />)
