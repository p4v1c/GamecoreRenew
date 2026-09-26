/**
 * Orbit's and Shelf's settings screens — what a pad can and cannot reach.
 *
 * Both are the host's shared screen with parts switched on: Orbit the index
 * layout and dialogs; the pager and inline detail are the host's too, and
 * tested here as options, though Shelf itself is back on the plain rail. None
 * of this is
 * visible in a diff of the markup, and every one of these has a failure a
 * player meets with a controller in hand:
 *
 *   · Back walks up one level at a time, and lands on the row it left;
 *   · a dialog owns the pad — nothing behind it answers, L1/R1 included;
 *   · the press that opens a confirmation cannot also answer it;
 *   · Bluetooth is the two-column page on Orbit too, with Forget on it;
 *   · Settings stands on the theme's own Home background, not a copy of it.
 *
 * No device is touched: every endpoint is answered by the stub below, and the
 * destructive ones are recorded rather than performed.
 */
import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createElement } from 'react'
import { buildSdk } from '../lib/themeSdk'
import { useStore } from '../store'

const SHARED = '../settings'
async function load(path: string) {
  return await import(/* @vite-ignore */ path)
}

const PAD = { mac: 'E4:17:D8:2A:9C:03', name: 'DualSense Wireless Controller', connected: true, paired: true }
let paired = [PAD]
let found: { mac: string, name: string, connected: boolean, paired: boolean }[] = []
let calls: { method: string, url: string }[] = []

const BOX: [string, () => unknown][] = [
  ['/api/settings/wifi/status', () => ({ connected: true, ssid: 'Home', ip: '192.168.1.34',
    gateway: '192.168.1.1', dns: ['9.9.9.9'], mac: 'DC:A6:32:11:8F:04', ethernet: { connected: false } })],
  ['/api/settings/wifi/networks', () => [
    { ssid: 'Home', signal: 82, secured: true, connected: true },
    { ssid: 'Guests', signal: 64, secured: true, connected: false }]],
  ['/api/settings/wifi/details', () => [{ ssid: 'Guests', security: 'WPA2', channel: 6, band: '2.4 GHz', rate: '144 Mb/s' }]],
  ['/api/settings/bluetooth/scan', () => ({ ok: true, seconds: 10, found })],
  ['/api/settings/bluetooth/devices/', () => {
    paired = []
    return { ok: true, message: 'Forgotten — pair it again to reconnect' }
  }],
  ['/api/settings/bluetooth/devices', () => paired],
  ['/api/settings/display/scale', () => ({ scale: 1, choices: [0.9, 1, 1.25, 1.5] })],
  ['/api/settings/display/mode', () => ({ ok: true, changed: true, revert_secs: 12 })],
  ['/api/settings/display/revert', () => ({ ok: true, reverted: true })],
  ['/api/settings/display/confirm', () => ({ ok: true, confirmed: true })],
  ['/api/settings/display', () => ({ output: 'HDMI-A-1', pending: false, revert_secs: 12,
    modes: [{ width: 1920, height: 1080, rate: 60 }, { width: 1280, height: 720, rate: 60 }],
    current: { width: 1920, height: 1080, rate: 60 } })],
  ['/api/themes', () => ({ sdk_version: 7, active: 'orbit', themes: [] })],
  ['/api/sysinfo', () => ({ version: '1.2.40', controllers: [] })],
  ['/api/systems', () => []],
]

beforeEach(() => {
  paired = [PAD]
  found = []
  calls = []
  useStore.setState({ screen: 'home', modalDepth: 0, standby: 'off', powerPending: null,
    sessionGameKey: null, sessionSystemId: null, backgroundSessions: [], transition: null } as never)
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push({ method: init?.method || 'GET', url })
    const hit = BOX.find(([k]) => (k.endsWith('/') ? url.includes(k) : url.endsWith(k)))
    const body = hit ? hit[1]() : url.includes('/playtime') ? [] : {}
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const press = async (name: string) => {
  await act(async () => { window.dispatchEvent(new CustomEvent(`gp:${name}`)) })
}

/** Past the dialog's arming delay — the press that opened it is spent. */
const later = () => vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 5000)

async function screen(parts: Record<string, unknown>, onClose = vi.fn()) {
  const { createSettings } = await load(`${SHARED}/screen.js`)
  const View = createSettings(buildSdk('orbit', { selectTheme: vi.fn(async () => {}) }), {}, parts)
  const r = render(createElement(View, { onClose }))
  return { ...r, onClose }
}

const text = (c: HTMLElement) => c.textContent || ''

describe('what is gone from both screens', () => {
  it.each([
    ['Orbit', { layout: 'index', detail: 'dialog' }],
    ['Shelf', { pager: true, detail: 'inline' }],
  ])('%s has no General category and no mapping actions', async (_, parts) => {
    const { container } = await screen(parts)
    const labels = [...container.querySelectorAll('.gcs-set-label b')].map(b => b.textContent)
    expect(labels).toEqual(['Wi-Fi', 'Bluetooth', 'Display', 'Audio', 'Controllers',
      'Emulators & apps', 'BIOS', 'Themes', 'System'])
    expect(text(container)).not.toMatch(/General|Scan mapping|Forget mapping/)
  })

  it('opens Shelf on Wi-Fi', async () => {
    const { container } = await screen({ pager: true, detail: 'inline' })
    await waitFor(() => expect(container.querySelector('.gcs-set-page')?.getAttribute('data-cat')).toBe('wifi'))
    expect(text(container)).toContain('Page 1, Connections')
  })
})

describe('Orbit — one page at a time', () => {
  it('opens the focused category, and Back returns to the list on the same row', async () => {
    const { container, onClose } = await screen({ layout: 'index', detail: 'dialog' })
    const focused = () => container.querySelector('.gcs-set-index-row[data-on="1"] b')?.textContent

    await press('dpad-down'); await press('dpad-down')
    expect(focused()).toBe('Display')
    await press('confirm')
    expect(container.querySelector('.gcs-set-title')?.textContent).toBe('Display')
    expect(container.querySelector('.gcs-set-index')).toBeNull()

    await press('back')
    expect(container.querySelector('.gcs-set-title')?.textContent).toBe('Settings')
    expect(focused()).toBe('Display')
    expect(onClose).not.toHaveBeenCalled()

    await press('back')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not leave a page on ←, where there is nowhere to go', async () => {
    const { container } = await screen({ layout: 'index', detail: 'dialog' })
    await press('dpad-down'); await press('dpad-down'); await press('confirm')
    await waitFor(() => expect(container.querySelector('.gcs-row2')).toBeTruthy())
    await press('dpad-left')
    expect(container.querySelector('.gcs-set-title')?.textContent).toBe('Display')
  })

  it('shows a network in a dialog, and ○ closes only the dialog', async () => {
    const { container } = await screen({ layout: 'index', detail: 'dialog' })
    await press('confirm')
    await waitFor(() => expect(container.querySelectorAll('.gcs-wifi-row').length).toBe(2))
    expect(container.querySelector('.gcs-set-aside')).toBeNull()

    await press('confirm')
    const dialog = container.querySelector('[role="dialog"]')!
    expect(dialog.textContent).toContain('Home')
    expect(dialog.textContent).toContain('192.168.1.34')

    await press('back')
    expect(container.querySelector('[role="dialog"]')).toBeNull()
    expect(container.querySelector('.gcs-set-title')?.textContent).toBe('Wi-Fi')
  })

  it('asks for a secured network\'s password on the on-screen keyboard', async () => {
    const { container } = await screen({ layout: 'index', detail: 'dialog' })
    await press('confirm')
    await waitFor(() => expect(container.querySelectorAll('.gcs-wifi-row').length).toBe(2))
    await press('dpad-down'); await press('confirm')
    later()
    await press('confirm')   // Connect, the dialog's first action
    await waitFor(() => expect(container.querySelector('.gcs-set-kb button')).toBeTruthy())
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Guests')
  })
})

describe('a dialog owns the pad', () => {
  const openDisplayConfirm = async (container: HTMLElement, keys: string[]) => {
    for (const k of keys) await press(k)
    await waitFor(() => expect(container.querySelectorAll('.gcs-row2').length).toBe(4))
    await press('dpad-right')          // 1280 × 720
    await press('dpad-down'); await press('dpad-down'); await press('confirm')
    await waitFor(() => expect(container.querySelector('[role="dialog"]')?.textContent)
      .toContain('Keep these display settings?'))
  }

  it('ignores the confirm that arrives with it, and answers a later one', async () => {
    const { container } = await screen({ layout: 'index', detail: 'dialog' })
    await openDisplayConfirm(container, ['dpad-down', 'dpad-down', 'confirm'])   // Display
    const answered = () => calls.some(c => /\/display\/(confirm|revert)$/.test(c.url))

    await press('confirm')   // at once: a held or repeated press — ignored
    expect(container.querySelector('[role="dialog"]')).toBeTruthy()
    expect(answered()).toBe(false)

    later()
    await press('confirm')   // deliberate
    await waitFor(() => expect(answered()).toBe(true))
  })

  it('keeps L1/R1 and the rail still while it is open (pager)', async () => {
    const { container } = await screen({ pager: true, detail: 'inline' })
    const cat = () => container.querySelector('.gcs-set-page')?.getAttribute('data-cat')
    await openDisplayConfirm(container, ['r1', 'r1', 'dpad-right'])
    expect(cat()).toBe('display')

    await press('r1'); await press('l1'); await press('dpad-up')
    expect(cat()).toBe('display')
    expect(container.querySelector('.gcs-set-row[data-on="1"]')).toBeNull()
  })
})

describe('Orbit — Bluetooth is the two-column page, with Forget', () => {
  it('lists Paired and Nearby side by side, and forgets on the second press', async () => {
    found = [{ mac: '7C:ED:8D:12:04:B1', name: '8BitDo Pro 2', connected: false, paired: false }]
    const { container } = await screen({ layout: 'index', detail: 'dialog' })
    await press('dpad-down'); await press('confirm')                  // Bluetooth
    await waitFor(() => expect(container.querySelector('.gcs-bt-forget')).toBeTruthy())
    expect(container.querySelector('.gcs-bt-col[data-col="paired"]')?.textContent).toContain(PAD.name)
    await waitFor(() => expect(container.querySelector('.gcs-bt-col[data-col="nearby"]')?.textContent)
      .toContain('8BitDo Pro 2'))

    await press('dpad-right'); await press('confirm')                  // Forget, armed
    expect(calls.some(c => c.method === 'DELETE')).toBe(false)
    await press('confirm')
    await waitFor(() => expect(calls.some(c => c.method === 'DELETE')).toBe(true))
    await waitFor(() => expect(text(container)).toContain('Nothing is paired yet.'))
  })

  it('does not leave the page on ←, and ○ goes back up to the list', async () => {
    const { container, onClose } = await screen({ layout: 'index', detail: 'dialog' })
    await press('dpad-down'); await press('confirm')
    await waitFor(() => expect(container.querySelector('.gcs-bt-forget')).toBeTruthy())
    await press('dpad-left')
    expect(container.querySelector('.gcs-bt-cols')).toBeTruthy()
    await press('back')
    await waitFor(() => expect(container.querySelector('.gcs-set-index')).toBeTruthy())
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('Display — the confirmation is a dialog, and doing nothing reverts', () => {
  it('reverts on ○, through the backend', async () => {
    const { container } = await screen({ pager: true, detail: 'inline' })
    await press('r1'); await press('r1'); await press('dpad-right')
    await waitFor(() => expect(container.querySelectorAll('.gcs-row2').length).toBe(4))
    await press('dpad-right')          // 1280 × 720
    await press('dpad-down'); await press('dpad-down'); await press('confirm')
    const dialog = () => container.querySelector('[role="dialog"]')
    await waitFor(() => expect(dialog()?.textContent).toContain('Keep these display settings?'))
    expect(dialog()?.textContent).toContain('1280 × 720')

    await press('back')
    await waitFor(() => expect(calls.some(c => c.url.endsWith('/display/revert'))).toBe(true))
    expect(dialog()).toBeNull()
    expect(calls.some(c => c.url.endsWith('/display/confirm'))).toBe(false)
  })
})

describe('Display — Scale', () => {
  it('applies the interface size at once and saves it, with no countdown', async () => {
    const setUiScale = vi.fn()
    vi.stubGlobal('gamecore', { setUiScale })
    const { container } = await screen({ pager: true, detail: 'inline' })
    await press('r1'); await press('r1'); await press('dpad-right')
    await waitFor(() => expect(container.querySelectorAll('.gcs-row2').length).toBe(4))
    expect(text(container)).toContain('Scale')
    expect(text(container)).toContain('100 %')
    await press('dpad-down'); await press('dpad-down'); await press('dpad-down')
    await press('dpad-right')          // 125 %
    await waitFor(() => expect(setUiScale).toHaveBeenCalledWith(1.25))
    expect(calls.some(c => c.method === 'POST' && c.url.endsWith('/display/scale'))).toBe(true)
    expect(container.querySelector('[role="dialog"]')).toBeNull()
  })
})

describe('the background is Home\'s own', () => {
  it('draws the component it is handed, and no fill of its own', async () => {
    const Wall = () => createElement('div', { className: 'home-wall' })
    const { container } = await screen({ pager: true, detail: 'inline', Background: Wall })
    const root = container.querySelector('.gcs-set')!
    expect(root.getAttribute('data-bg')).toBe('theme')
    expect(root.querySelector('.gcs-set-bg .home-wall')).toBeTruthy()
    expect(root.querySelector('.gcs-set-paper')).toBeNull()
  })

  it('orbit hands Settings its own backdrop: the gear movement, not Home\'s art', async () => {
    const theme = (await load('../../../config/themes/orbit/index.js')).default(
      buildSdk('orbit', { selectTheme: vi.fn(async () => {}) }))
    const r = render(createElement(theme.shell))
    await waitFor(() => expect(r.container.querySelector('.scenery')).toBeTruthy())
    await press('menu')
    const settings = await waitFor(() => {
      const el = r.container.querySelector('.gcs-set')
      expect(el).toBeTruthy()
      return el!
    })
    expect(settings.getAttribute('data-bg')).toBe('theme')
    expect(settings.querySelector('.gcs-set-bg .orbit-gears svg animateTransform')).toBeTruthy()
    expect(settings.querySelector('.gcs-set-bg .scenery')).toBeNull()
  })
})
