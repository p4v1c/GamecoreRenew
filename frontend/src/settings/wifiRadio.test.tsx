/**
 * The Wi-Fi radio switch on the shared settings page (every theme draws it).
 *
 * The box is faked through `fetch`: `radio` flips when the page POSTs, the way
 * NetworkManager would, and every request is recorded so a test can say what
 * the page did NOT ask (a scan with the radio off).
 */
import { render, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { buildSdk } from '../lib/themeSdk'

// Through a variable path, like shelfSettings.test.ts: plain .js, no
// declarations, and `npm run build` typechecks this file.
const SHARED = '../settings'
const { createWifiPage } = await import(/* @vite-ignore */ `${SHARED}/wifi.js`)
const { createUseSlow } = await import(/* @vite-ignore */ `${SHARED}/slow.js`)

type View = React.ComponentType<Record<string, unknown>>

let box: { radio: boolean | undefined; wired: boolean; nets: unknown[] }
let calls: { method: string; url: string; body?: string }[]

const NETS = [
  { ssid: 'Home', signal: 82, secured: true, connected: true },
  { ssid: 'Guests', signal: 64, secured: true, connected: false },
]

beforeEach(() => {
  cleanup()
  box = { radio: true, wired: false, nets: NETS }
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method || 'GET'
    calls.push({ method, url, body: init?.body as string | undefined })
    let body: unknown = {}
    if (url.endsWith('/settings/wifi/status')) {
      body = { connected: box.radio !== false, ssid: 'Home', ip: '10.0.0.2', radio: box.radio,
               ethernet: { connected: box.wired, iface: '', ip: '' } }
    } else if (url.endsWith('/settings/wifi/networks')) {
      body = box.radio === false ? [] : box.nets
    } else if (url.endsWith('/settings/wifi/details')) {
      body = []
    } else if (url.endsWith('/settings/wifi/radio')) {
      box.radio = JSON.parse(String(init?.body)).enabled
      body = { enabled: box.radio }
    }
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
})

const draw = () => {
  const sdk = buildSdk('', { selectTheme: vi.fn(async () => {}) })
  const Page = createWifiPage(sdk, createUseSlow(sdk)) as View
  return render(<Page active={true} onLeave={() => {}} />).container
}

const radioRow = (c: HTMLElement) => c.querySelector('[role="switch"]') as HTMLElement
const posts = () => calls.filter(c => c.method === 'POST' && c.url.endsWith('/wifi/radio'))

describe('the Wi-Fi radio switch', () => {
  it('asks twice before cutting the only connection, then hides the list', async () => {
    const c = draw()
    await waitFor(() => expect(c.querySelectorAll('.gcs-wifi-row').length).toBe(2))
    expect(radioRow(c).getAttribute('aria-checked')).toBe('true')

    fireEvent.click(radioRow(c))
    expect(radioRow(c).textContent).toContain('Press again to turn Wi-Fi off')
    expect(posts()).toHaveLength(0)

    fireEvent.click(radioRow(c))
    await waitFor(() => expect(radioRow(c).getAttribute('aria-checked')).toBe('false'))
    expect(JSON.parse(posts()[0].body!)).toEqual({ enabled: false })
    expect(c.querySelectorAll('.gcs-wifi-row')).toHaveLength(0)
    expect(c.textContent).toContain('Wi-Fi is off.')
    expect(c.querySelector('.gcs-load')).toBeNull()
    expect(c.querySelector('.gcs-wifi-scan')).toBeNull()
    expect(c.textContent).not.toMatch(/No network/)
  })

  it('turns off in one press when a cable keeps the box online', async () => {
    box.wired = true
    const c = draw()
    await waitFor(() => expect(radioRow(c)).toBeTruthy())
    fireEvent.click(radioRow(c))
    await waitFor(() => expect(posts()).toHaveLength(1))
  })

  it('does not scan while the radio is off, and turns it on in one press', async () => {
    box.radio = false
    const c = draw()
    await waitFor(() => expect(radioRow(c).getAttribute('aria-checked')).toBe('false'))
    expect(calls.some(x => x.url.endsWith('/wifi/networks'))).toBe(false)

    fireEvent.click(radioRow(c))
    await waitFor(() => expect(c.querySelectorAll('.gcs-wifi-row').length).toBe(2))
    expect(JSON.parse(posts()[0].body!)).toEqual({ enabled: true })
  })

  it('says it is scanning, not that nothing is in range, right after turning on', async () => {
    // NetworkManager has not scanned yet when the radio comes up, so the
    // first answer is empty.
    box.radio = false
    box.nets = []
    const c = draw()
    await waitFor(() => expect(radioRow(c)).toBeTruthy())
    fireEvent.click(radioRow(c))
    await waitFor(() => expect(posts()).toHaveLength(1))
    await waitFor(() => expect(calls.some(x => x.url.endsWith('/wifi/networks'))).toBe(true))
    expect(c.querySelector('.gcs-load')).toBeTruthy()
    expect(c.textContent).not.toMatch(/No network is in range/)
  })

  it('stops saying it is scanning once a real scan finds nothing', async () => {
    // Only NetworkManager's first answer after the radio comes up is "not
    // yet"; a place with no network at all must not scan for ever.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      box.radio = false
      box.nets = []
      const c = draw()
      await waitFor(() => expect(radioRow(c)).toBeTruthy())
      fireEvent.click(radioRow(c))
      await waitFor(() => expect(c.querySelector('.gcs-load')).toBeTruthy())
      await vi.advanceTimersByTimeAsync(10000)
      await waitFor(() => expect(c.textContent).toMatch(/No network is in range/))
    } finally {
      vi.useRealTimers()
    }
  })

  it('draws no switch for a backend that does not report the radio', async () => {
    box.radio = undefined
    const c = draw()
    await waitFor(() => expect(c.querySelectorAll('.gcs-wifi-row').length).toBe(2))
    expect(radioRow(c)).toBeNull()
  })

  it('shows the backend refusal instead of pretending', async () => {
    box.wired = true
    const c = draw()
    await waitFor(() => expect(radioRow(c)).toBeTruthy())
    vi.mocked(fetch).mockImplementationOnce(async () => ({
      ok: false, status: 502, statusText: 'Bad Gateway',
      json: async () => ({ detail: 'Error: Not authorized to control networking.' }),
    }) as Response)
    fireEvent.click(radioRow(c))
    await waitFor(() => expect(c.querySelector('.gcs-wifi-msg')?.textContent)
      .toContain('Not authorized'))
    expect(radioRow(c).getAttribute('aria-checked')).toBe('true')
  })
})
