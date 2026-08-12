/**
 * The default settings menu — the one the box falls back to.
 *
 * It is the surface a broken theme lands on, so what is asserted here is not
 * how it looks but that it still opens and still lists everything when the
 * services behind it are unreachable. A settings menu that fails to render
 * because Wi-Fi could not be reached is the last thing this screen may do.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import SettingsModal from './SettingsModal'

const BOX: Record<string, unknown> = {
  '/api/settings/wifi/status': { connected: true, ssid: 'patrice.5', ethernet: { connected: false } },
  '/api/settings/bluetooth/devices': [{ mac: 'a', name: 'Pad', connected: true, paired: true }],
  '/api/settings/audio/sinks': [{ id: '1', name: 'HDMI', default: true }],
  '/api/storage/volumes': { ok: true, volumes: [{ device: '/dev/sdb1' }] },
  '/api/standby': { enabled: true, screensaver_mins: 6, sleep_mins: 16, state: 'awake' },
  '/api/catalog': [{ id: 'a', installed: true }, { id: 'b', installed: false }],
  '/api/bios': [{ id: 'a', status: 'ok' }, { id: 'b', status: 'absent' }],
  '/api/sysinfo': { version: '1.0.172', controllers: [], bios: { ok: true, systems: {} } },
  '/api/themes': { sdk_version: 1, active: 'shelf', themes: [{ id: 'shelf', name: 'Shelf' }] },
}

const answer = (table: Record<string, unknown>) =>
  vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const hit = Object.keys(table).find(k => url.endsWith(k))
    if (!hit) return { ok: false, status: 404, statusText: 'nf', json: async () => ({}) }
    return { ok: true, status: 200, statusText: 'OK', json: async () => table[hit] }
  })

beforeEach(() => vi.stubGlobal('fetch', answer(BOX)))
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('the default settings menu', () => {
  it('reaches every page the host has', async () => {
    const defaults = await import('../defaults')
    render(<SettingsModal onClose={vi.fn()} />)
    for (const label of ['Wi-Fi', 'Audio', 'Bluetooth', 'Storage', 'Standby',
                         'Themes', 'Emulators & apps', 'BIOS', 'Update', 'Desktop Mode']) {
      expect(screen.getByText(label)).toBeTruthy()
    }
    // The count is the claim: a page added to the host and forgotten here is a
    // page the fallback cannot open, which is where "unreachable" started.
    expect(defaults.SETTINGS_PAGE_IDS).toHaveLength(10)
  })

  it('reads the value at the end of each row from the box', async () => {
    render(<SettingsModal onClose={vi.fn()} />)
    expect(await screen.findByText('patrice.5')).toBeTruthy()
    expect(await screen.findByText('1 connected')).toBeTruthy()
    expect(await screen.findByText('1/2 ready')).toBeTruthy()
    expect(await screen.findByText('v1.0.172')).toBeTruthy()
  })

  it('still opens, and still lists everything, when nothing answers', async () => {
    // The case that matters for a fallback: every service down. The menu is
    // what someone opens BECAUSE the box is misbehaving.
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('backend unreachable')
    }))
    render(<SettingsModal onClose={vi.fn()} />)
    expect(screen.getByText('Wi-Fi')).toBeTruthy()
    expect(screen.getByText('Desktop Mode')).toBeTruthy()
    // No invented reading anywhere.
    await waitFor(() => expect(screen.queryByText(/connected|ready|installed/)).toBeNull())
  })
})
