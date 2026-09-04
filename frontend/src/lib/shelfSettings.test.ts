/**
 * Shelf v2's two reworked surfaces, run against the real SDK.
 *
 * Modelled on defaultRemake.test.ts and for the same reason: a stub would pass
 * on the day the SDK stopped being able to express these screens. What is
 * asserted here is not how they look — nobody can test that — but the three
 * things that make them usable or not, and that no reviewer can see by reading
 * the markup:
 *
 *   · every row in the rail leads somewhere, and the four pages folded under
 *     `System` are still reachable. Omitting one is invisible on screen and has
 *     shipped twice;
 *   · the values at the end of the rows come from the box. The reference
 *     capture is full of plausible numbers with no source, and a rail that
 *     invents one is a rail nobody can trust for the ones that are real;
 *   · the power view renders every option it is handed, in the order it is
 *     handed them. `focusIdx` is an index into that array, so a view that
 *     drops or reorders rows sends the cursor somewhere the player is not
 *     looking — on the one screen where a mispress powers the box off.
 *
 * The theme is imported through a variable path so `tsc` treats it as dynamic:
 * `npm run build` typechecks this file, and these are plain .js modules with
 * no declarations.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { buildSdk } from './themeSdk'

const THEME = '../../../config/themes/shelf'
// The screen itself is the HOST's now — three surfaces draw it (Shelf, Summer,
// and the built-in default), so it lives in the bundle and reaches themes
// through `sdk.defaults`. Shelf is still what this file loads it AS: these
// tests are about the rail Shelf shows, and Shelf's sdk is what it is given.
const SHARED = '../settings'

const sdk = () => buildSdk('shelf', { selectTheme: vi.fn(async () => {}) })

async function load(path: string) {
  return await import(/* @vite-ignore */ path)
}

/**
 * What this box would answer. Every value below is shaped like the real
 * endpoint's response, because the point of the meta assertions is that the
 * rail reads THESE rather than carrying its own copy.
 */
const BOX: Record<string, unknown> = {
  '/api/settings/wifi/status': {
    connected: true, ssid: 'Livebox-4F2A', ip: '192.168.1.34', iface: 'wlp0s20f3',
    gateway: '192.168.1.1', dns: ['9.9.9.9'], mac: 'DC:A6:32:11:8F:04',
    ethernet: { connected: false, iface: '', ip: '' },
  },
  '/api/settings/wifi/networks': [
    { ssid: 'Livebox-4F2A', signal: 82, secured: true, connected: true },
    { ssid: 'FreeWifi_Secure', signal: 64, secured: true, connected: false },
    { ssid: 'Console-Hotspot', signal: 33, secured: false, connected: false },
  ],
  // A separate endpoint on purpose, and separate here too: the merge onto the
  // scan is what the page has to get right, and a single fixture would hide it.
  '/api/settings/wifi/details': [
    { ssid: 'Livebox-4F2A', security: 'WPA3', channel: 44, band: '5 GHz', rate: '866 Mb/s' },
    { ssid: 'FreeWifi_Secure', security: 'WPA2', channel: 100, band: '5 GHz', rate: '433 Mb/s' },
    { ssid: 'Console-Hotspot', security: 'Open', channel: 36, band: '5 GHz', rate: '200 Mb/s' },
  ],
  // A refusal, because that is the interesting half: the player retries, and
  // the prompt they are given the second time is what the test below is about.
  '/api/settings/wifi/connect': { ok: false, wrong_password: true, error: 'Wrong password' },
  '/api/settings/bluetooth/devices': [
    { mac: 'E4:17:D8:2A:9C:03', name: '8BitDo Ultimate 2C', connected: true, paired: true },
    { mac: 'A0:9E:1B:44:D2:18', name: 'Marshall Major IV', connected: false, paired: true },
  ],
  '/api/settings/display': {
    output: 'HDMI-A-1',
    modes: [
      { width: 1920, height: 1080, rate: 60 },
      { width: 1920, height: 1080, rate: 50 },
      { width: 1280, height: 720, rate: 60 },
    ],
    current: { width: 1920, height: 1080, rate: 60 },
    pending: false, revert_secs: 12,
  },
  '/api/settings/display/mode': { ok: true, changed: true, revert_secs: 12 },
  '/api/settings/display/confirm': { ok: true, confirmed: true },
  '/api/settings/display/revert': { ok: true, reverted: true },
  '/api/settings/audio/sinks': [
    { id: '49', name: 'Built-in Audio Analog Stereo', default: false },
    { id: '52', name: 'HDMI / DisplayPort', default: true },
  ],
  '/api/catalog': [
    { id: 'rpcs3', kind: 'emulator', label: 'PlayStation 3', installed: true },
    { id: 'cemu', kind: 'emulator', label: 'Wii U', installed: false },
    { id: 'mgba', kind: 'emulator', label: 'Game Boy Advance', installed: true },
  ],
  '/api/bios': [
    { id: 'pcsx2', label: 'PlayStation 2', status: 'ok', installed: true, files: [] },
    { id: 'cemu', label: 'Wii U', status: 'absent', installed: false, files: [] },
  ],
  '/api/themes': {
    sdk_version: 1, active: 'shelf',
    themes: [{ id: 'shelf', name: 'Shelf', version: '2.0.0', compatible: true }],
  },
  '/api/sysinfo': {
    ip: '192.168.1.34', storage_used_gb: 218, storage_total_gb: 320, storage_free_gb: 102,
    version: '1.0.160', controllers: [], bios: { ok: true, systems: {} },
  },
  '/api/standby': { state: 'awake', enabled: true, screensaver_mins: 6, sleep_mins: 16 },
  '/api/storage/volumes': { ok: true, volumes: [{ device: '/dev/sdb1', label: 'SANDISK' }] },
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(typeof input === 'string' ? input : (input as Request).url ?? input)
    const hit = Object.keys(BOX).find(k => url.endsWith(k))
    if (!hit) return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({}) }
    return { ok: true, status: 200, statusText: 'OK', json: async () => BOX[hit] }
  }))
})

// Unmount between tests rather than at the end of each one. A `cleanup()` on
// the last line of a test never runs when an assertion above it throws, and
// the leftover tree then makes every following `getByText` ambiguous — one
// real failure turns into three, and two of them point at the wrong test.
afterEach(async () => {
  const { cleanup } = await import('@testing-library/react')
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function renderRail() {
  const { createSettings } = await load(`${SHARED}/screen.js`)
  const View = createSettings(sdk())
  const { render } = await import('@testing-library/react')
  const { createElement } = await import('react')
  // As an element, not a call: the view holds state, and invoking it directly
  // would run its hooks outside a render.
  return render(createElement(View, { onClose: vi.fn() }))
}

/** The rail's rows, by label — the screen now names a category in three places
 *  (rail row, page heading, breadcrumb), so a text-wide query is ambiguous by
 *  construction and asking the rail directly is the honest question. */
const railLabels = (c: HTMLElement) =>
  [...c.querySelectorAll('.gcs-set-rail .gcs-set-row .gcs-set-label b')].map(e => e.textContent)
const railMetas = (c: HTMLElement) =>
  [...c.querySelectorAll('.gcs-set-rail .gcs-set-row .gcs-set-label i')].map(e => e.textContent)

describe('Shelf v2 — the settings rail', () => {
  it('declares every host settings page, and draws the eight the capture has', async () => {
    // check-theme.mjs proves the DECLARATION is complete. This proves the rail
    // that is actually drawn is the capture's — eight rows, not the ten ids.
    // The two are different numbers on purpose: `update`, `standby` and
    // `storage` are sections of the System page, and `desktop` is in the power
    // menu, which is where the capture puts leaving the front end.
    const defaults = await import('../components/defaults')
    const src = await load(`${THEME}/theme.json`)
    const declared: string[] = (src.default ?? src).settings.pages
    expect([...declared].sort()).toEqual([...defaults.SETTINGS_PAGE_IDS].sort())

    const { container } = await renderRail()
    expect(railLabels(container)).toEqual([
      'Wi-Fi', 'Bluetooth', 'Display', 'Audio', 'Controllers',
      'Emulators & apps', 'BIOS', 'Themes', 'System',
    ])
  })

  it('keeps the settings the four unlisted ids stand for reachable', async () => {
    // The declaration is about what a player can REACH, so this is the claim
    // that has to hold: update, standby and storage are all on the System page.
    const { screen, fireEvent, waitFor } = await import('@testing-library/react')
    const { container } = await renderRail()

    fireEvent.click(screen.getAllByText('System')[0])
    await waitFor(() => expect(container.textContent).toMatch(/System update/))
    expect(container.textContent).toMatch(/Standby mode/)
    expect(container.textContent).toMatch(/Storage/)
  })

  it('reads the value at the end of each row from the box', async () => {
    // The assertion the reference capture fails: its rail says "−42 dBm" and
    // "82 %" and nothing on this machine produces either.
    const { container } = await renderRail()
    const { waitFor } = await import('@testing-library/react')
    await waitFor(() => expect(railMetas(container)[0]).toBe('Livebox-4F2A'))
    const metas = railMetas(container)
    expect(metas[1]).toBe('1 connected')          // bluetooth devices
    expect(metas[3]).toBe('HDMI / DisplayPort')   // default sink
    expect(metas[5]).toBe('2 installed')          // catalog
    expect(metas[6]).toBe('1/2 ready')            // bios status verdict
    expect(metas[7]).toBe('Shelf')                // active theme
  })

  it('leaves a row blank when its endpoint does not answer', async () => {
    // Not cosmetic. A rail that falls back to a plausible string when a service
    // is down lies exactly when the box is broken — which is when someone opens
    // it.
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false, status: 503, statusText: 'Service Unavailable', json: async () => ({}),
    })))
    const { container } = await renderRail()

    expect(railLabels(container)).toHaveLength(9)
    // Eight are fed by an endpoint and go blank with it. The ninth —
    // Controllers, row five — counts pads through the Gamepad API, which is the
    // browser and is still up. The row that says whether a pad is connected
    // must not go dark because a backend service did. Its index is derived
    // rather than written down: the rail has gained a row twice now, and a
    // literal here silently starts asserting about the wrong one.
    const controllersRow = railLabels(container).indexOf('Controllers')
    railMetas(container).forEach((m, i) => {
      if (i === controllersRow) expect(m).toMatch(/\d+ pads?$/)
      else expect(m).toBe('')
    })
  })

  it('names the category in the breadcrumb, and follows the rail cursor', async () => {
    const { screen, fireEvent } = await import('@testing-library/react')
    const { container } = await renderRail()

    expect(container.querySelector('.gcs-set-chip')?.textContent).toBe('WI-FI')
    fireEvent.click(screen.getAllByText('System')[0])
    expect(container.querySelector('.gcs-set-chip')?.textContent).toBe('SYSTEM')
    // The rail never leaves — that is the whole shape of this screen — so the
    // eight rows are still there with a different one selected.
    expect(railLabels(container)).toHaveLength(9)
    expect(container.querySelector('.gcs-set-row[data-sel="1"] .gcs-set-label b')?.textContent)
      .toBe('System')
  })

  it('gives every rail row a page, and says so in words if one ever goes missing', async () => {
    // Two halves of one invariant. Every category resolves to a page — that is
    // what the rewrite finished — and a category that ever stops resolving
    // renders as a sentence rather than as `undefined` handed to React, which
    // throws and, under the shell's error boundary, hands the whole frontend
    // back to the default. A theme going dark because one page was renamed is
    // the quiet failure worth answering in words.
    const { createSettings } = await load(`${SHARED}/screen.js`)
    const { render, screen, fireEvent } = await import('@testing-library/react')
    const { createElement } = await import('react')

    const { container } = render(createElement(createSettings(sdk()), { onClose: vi.fn() }))
    for (const label of railLabels(container)) {
      fireEvent.click(screen.getAllByText(String(label))[0])
      expect(container.querySelector('.gcs-set-main')).toBeTruthy()
      expect(container.textContent).not.toMatch(/This build has no/)
    }

    // Now knock one out through the documented seam and watch it say so.
    const holed = createSettings(sdk(), { inline: { bios: null } })
    const { container: c2 } = render(createElement(holed, { onClose: vi.fn() }))
    fireEvent.click([...c2.querySelectorAll('.gcs-set-rail .gcs-set-row')]
      .find(r => r.textContent?.includes('BIOS'))!)
    expect(c2.textContent).toMatch(/This build has no .*bios.* page/)
  })
})

describe('Shelf v2 — the Wi-Fi page', () => {
  it('draws the scan, and merges the radio detail onto it', async () => {
    const { screen, waitFor } = await import('@testing-library/react')
    const { container } = await renderRail()

    // Every SSID from /networks, in the order the backend ranked them. Awaited:
    // the scan is a fetch, and asserting before it lands tests the empty state.
    await waitFor(() =>
      expect(container.querySelectorAll('.gcs-wifi-row').length).toBe(3))
    const names = [...container.querySelectorAll('.gcs-wifi-row .gcs-wifi-name b')]
      .map(e => e.textContent)
    expect(names).toEqual(['Livebox-4F2A', 'FreeWifi_Secure', 'Console-Hotspot'])

    // Band and channel come from /details, which is a different endpoint —
    // this is the merge, and it is keyed on ssid.
    expect(await screen.findByText('5 GHz · channel 44 · 82%')).toBeTruthy()
    // Security label too: "Open" rather than the `secured: false` boolean.
    expect(screen.getByText('Open')).toBeTruthy()
  })

  it('fills the detail column from the box, and omits what it has no value for', async () => {
    const { screen, waitFor } = await import('@testing-library/react')
    const { container } = await renderRail()
    await waitFor(() =>
      expect(container.querySelectorAll('.gcs-set-fact').length).toBeGreaterThan(4))

    const facts = Object.fromEntries(
      [...container.querySelectorAll('.gcs-set-fact')]
        .map(f => [f.querySelector('dt')?.textContent, f.querySelector('dd')?.textContent]))

    expect(facts).toMatchObject({
      Status: 'Connected',
      'IP address': '192.168.1.34',
      Gateway: '192.168.1.1',
      DNS: '9.9.9.9',
      Security: 'WPA3',
      'MAC address': 'DC:A6:32:11:8F:04',
    })
    expect(screen.getByText('Disconnect')).toBeTruthy()
  })

  it('drops a detail row rather than printing it blank', async () => {
    // A box whose nmcli cannot answer for gateway or MAC. An empty "Gateway"
    // row reads as "this network has none", which is a different and wrong
    // statement — so the row is not drawn at all.
    const thin: Record<string, unknown> = {
      ...BOX,
      '/api/settings/wifi/status': {
        connected: true, ssid: 'Livebox-4F2A', ip: '192.168.1.34', iface: 'w0',
        gateway: '', dns: [], mac: '',
        ethernet: { connected: false, iface: '', ip: '' },
      },
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      const hit = Object.keys(thin).find(k => url.endsWith(k))
      if (!hit) return { ok: false, status: 404, statusText: 'nf', json: async () => ({}) }
      return { ok: true, status: 200, statusText: 'OK', json: async () => thin[hit] }
    }))

    const { container } = await renderRail()
    const { waitFor } = await import('@testing-library/react')
    await waitFor(() => expect(container.querySelectorAll('.gcs-set-fact').length).toBeGreaterThan(0))

    const keys = [...container.querySelectorAll('.gcs-set-fact dt')].map(e => e.textContent)
    expect(keys).toContain('IP address')
    expect(keys).not.toContain('Gateway')
    expect(keys).not.toContain('DNS')
    expect(keys).not.toContain('MAC address')
  })
})

describe('Shelf v2 — the power menu', () => {
  it('renders every option it is handed, in the order it is handed them', async () => {
    // `focusIdx` is an index into `options`. A view that hides a row it does
    // not like leaves the cursor landing on nothing; one that reorders them
    // sends it jumping. Both are invisible until someone holds down and
    // shuts the box off by accident.
    const { createPowerView } = await load(`${SHARED}/power.js`)
    const View = createPowerView(sdk())
    const PowerModal = await import('../components/modals/PowerModal')
    expect(PowerModal.default).toBeTruthy()

    const options = [
      // The unfiltered list, on purpose: this asserts the view renders whatever
      // it is handed, including the two ids Shelf asks the host to omit. A view
      // that quietly dropped them would pass a test built from the filtered list
      // and still misplace the cursor for any theme that keeps them.
      { id: 'scan', label: 'Scan mapping', busy: 'Scanning…', icon: '◎', color: '#22c55e', desc: 'a' },
      { id: 'forget', label: 'Forget mapping', busy: 'Forgetting…', icon: '⌫', color: '#64748b', desc: 'b' },
      { id: 'shutdown', label: 'Shutdown', busy: 'Shutting down…', icon: '⏻', color: '#ef4444', desc: 'c' },
      { id: 'restart', label: 'Restart', busy: 'Restarting…', icon: '↺', color: '#f59e0b', desc: 'd' },
      { id: 'desktop', label: 'Return to desktop', busy: 'Leaving…', icon: '⌘', color: '#38bdf8', desc: 'e' },
    ]

    const { render, screen } = await import('@testing-library/react')
    const { createElement } = await import('react')
    // The props object typed, the component left alone: casting the props to
    // `never` makes createElement infer a `CElement<never>` that render() then
    // refuses. The view comes from a dynamic import and is already `any`.
    const props: Record<string, unknown> = {
      options, focusIdx: 0, confirmId: null, pendingId: null,
      scanning: false, scanResult: null,
      onFocus: vi.fn(), onActivate: vi.fn(), onCancel: vi.fn(),
    }
    const { container } = render(createElement(View, props))

    for (const o of options) expect(screen.getByText(o.label)).toBeTruthy()

    const rows = [...container.querySelectorAll('.gcs-pwr-row')]
    expect(rows).toHaveLength(options.length)
    expect(rows.map(r => r.querySelector('.gcs-pwr-text b')?.textContent))
      .toEqual(options.map(o => o.label))

  })

  it('lets a theme move the mapping utilities out, but never the way off the box', async () => {
    // The filter is the host's, not the view's: `focusIdx` indexes the array
    // handed over, so a view hiding rows itself would leave the cursor landing
    // on nothing. And a theme with a typo in its omit list must not be able to
    // build a console that cannot be turned off from the sofa.
    const PowerModal = (await import('../components/modals/PowerModal')).default
    const { render } = await import('@testing-library/react')
    const { createElement } = await import('react')

    const seen: string[][] = []
    const Spy = (props: { options: { id: string }[] }) => {
      seen.push(props.options.map(o => o.id))
      return null
    }

    render(createElement(PowerModal, {
      onClose: vi.fn(), view: Spy as never, omit: ['scan', 'forget'],
    }))
    expect(seen[seen.length - 1]).toEqual(['shutdown', 'restart', 'desktop'])

    seen.length = 0
    render(createElement(PowerModal, {
      onClose: vi.fn(), view: Spy as never, omit: ['shutdown', 'restart', 'desktop', 'scan'],
    }))
    // Everything that ends a session survives the request; only `scan` goes.
    expect(seen[seen.length - 1]).toEqual(['forget', 'shutdown', 'restart', 'desktop'])

    seen.length = 0
    render(createElement(PowerModal, { onClose: vi.fn(), view: Spy as never }))
    expect(seen[seen.length - 1]).toEqual(['scan', 'forget', 'shutdown', 'restart', 'desktop'])
  })
})

describe('Shelf v2 — the Controllers page', () => {
  const withPads = (pads: unknown[]) =>
    vi.stubGlobal('navigator', Object.assign(
      Object.create(Object.getPrototypeOf(navigator)), navigator, { getGamepads: () => pads }))

  async function renderControllers() {
    const { createRows } = await load(`${SHARED}/rows.js`)
    const { createControllersPage } = await load(`${SHARED}/controllers.js`)
    const s = sdk()
    const View = createControllersPage(s, createRows(s))
    const { render } = await import('@testing-library/react')
    const { createElement } = await import('react')
    return render(createElement(View, { active: true, onLeave: vi.fn() }))
  }

  it('lists pads from the Gamepad API, not from the battery scan', async () => {
    // sysinfo.controllers is read_batteries(), a sysfs scan that only sees pads
    // exposing a battery. A wired pad has none, so counting it there would
    // report "no pad" on the one screen whose job is to say whether one is
    // connected — while the player is holding it.
    withPads([{ index: 0, id: 'Wired Controller (Vendor: 045e)' }])
    const { container } = await renderControllers()
    expect(container.textContent).toMatch(/Player 1/)
    expect(container.textContent).toMatch(/Wired Controller \(Vendor: 045e\)/)
  })

  it('arms Forget mapping before it fires, and disarms when focus moves', async () => {
    // The protection that had to survive the move out of PowerModal. It deletes
    // work the owner did by hand inside an emulator's own input UI, and there
    // is no undo anywhere on this box.
    withPads([])
    const { container } = await renderControllers()
    const { fireEvent } = await import('@testing-library/react')

    const rowFor = (text: string) => [...container.querySelectorAll('.gcs-row2')]
      .find(r => r.textContent?.includes(text))!

    fireEvent.click(rowFor('Forget mapping'))
    expect(container.textContent).toMatch(/Press again to forget/)

    // Moving the cursor elsewhere must take the primed row back down.
    fireEvent.click(rowFor('Scan mapping'))
    expect(container.textContent).not.toMatch(/Press again to forget/)
  })

  it('carries no control the box cannot honour', async () => {
    // The capture draws a stick dead zone and an exit-combination picker.
    // Neither exists: dead zones are written per emulator by configgen and the
    // exit hotkey is generated rather than chosen. A slider governing nothing
    // is worse than an absent one.
    withPads([])
    const { container } = await renderControllers()
    expect(container.textContent).not.toMatch(/dead zone/i)
    expect(container.textContent).not.toMatch(/Exit combination/i)
  })
})

describe('Shelf v2 — what a page shows before its data arrives', () => {
  /** A fetch that never settles: the state between opening a page and the box
   *  answering, which is the state the owner was actually seeing. */
  const stall = () => vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))

  async function renderPage(name: 'wifi' | 'bluetooth') {
    const { createSettings } = await load(`${SHARED}/screen.js`)
    const { render, fireEvent } = await import('@testing-library/react')
    const { createElement } = await import('react')
    const { container } = render(createElement(createSettings(sdk()), { onClose: vi.fn() }))
    if (name === 'bluetooth') {
      const row = [...container.querySelectorAll('.gcs-set-rail .gcs-set-row')]
        .find(r => r.textContent?.includes('Bluetooth'))!
      fireEvent.click(row)
    }
    return container
  }

  it('says it is still asking, rather than that there is nothing', async () => {
    // The bug as reported: opening Bluetooth greeted a box with two paired pads
    // by announcing it had none, because "no devices yet" and "no devices" were
    // the same empty array. Same shape on Wi-Fi, which claimed no network was
    // in range while connected to one.
    stall()
    const bt = await renderPage('bluetooth')
    expect(bt.querySelector('.gcs-load')).toBeTruthy()
    expect(bt.textContent).not.toMatch(/Nothing is paired yet/)

    const wifi = await renderPage('wifi')
    expect(wifi.querySelector('.gcs-load')).toBeTruthy()
    expect(wifi.textContent).not.toMatch(/No network is in range/)
    expect(wifi.textContent).not.toMatch(/No networks are in range/)
  })

  it('still says "nothing" once the box has actually answered nothing', async () => {
    // The other half. A guard that never resolves would trade a wrong message
    // for a spinner that spins for ever, which is not an improvement.
    const empty: Record<string, unknown> = { ...BOX, '/api/settings/bluetooth/devices': [] }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      const hit = Object.keys(empty).find(k => url.endsWith(k))
      if (!hit) return { ok: false, status: 404, statusText: 'nf', json: async () => ({}) }
      return { ok: true, status: 200, statusText: 'OK', json: async () => empty[hit] }
    }))
    const { waitFor } = await import('@testing-library/react')
    const bt = await renderPage('bluetooth')
    await waitFor(() => expect(bt.textContent).toMatch(/Nothing is paired yet/))
    expect(bt.querySelector('.gcs-load')).toBeNull()
  })

  it('opens with what the rail already fetched instead of asking twice', async () => {
    // The rail fetches the paired list to put "1 connected" at the end of the
    // Bluetooth row. Handing that to the page is the difference between opening
    // on the list and opening on a spinner.
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      calls.push(url)
      const hit = Object.keys(BOX).find(k => url.endsWith(k))
      // The page's own refetch never lands, so anything on screen came from the
      // seed rather than from a second request.
      if (calls.filter(c => c.endsWith('/api/settings/bluetooth/devices')).length > 1) {
        return new Promise(() => {}) as never
      }
      if (!hit) return { ok: false, status: 404, statusText: 'nf', json: async () => ({}) }
      return { ok: true, status: 200, statusText: 'OK', json: async () => BOX[hit] }
    }))
    const { waitFor } = await import('@testing-library/react')
    const bt = await renderPage('bluetooth')
    await waitFor(() => expect(bt.textContent).toMatch(/8BitDo Ultimate 2C/))
  })
})

describe('the shared screen — the host parts it borrows', () => {
  it('puts the on-screen keyboard on a surface of its own', async () => {
    // VirtualKeyboard draws itself in hardcoded white on a black field; only
    // its accent is a variable. Shelf's password dialog is paper, so the
    // keyboard shipped invisible — white letters at 1.05:1 against the card
    // behind them. The wrapper is what each theme paints so that cannot happen
    // again, and its absence is not visible in any screenshot of a theme whose
    // dialog is already dark.
    const { createWifiPage } = await load(`${SHARED}/wifi.js`)
    const { createUseSlow } = await load(`${SHARED}/slow.js`)
    const s = sdk()
    const View = createWifiPage(s, createUseSlow(s))
    const { render, waitFor, fireEvent } = await import('@testing-library/react')
    const { createElement } = await import('react')
    const { container } = render(createElement(View, { active: true, onLeave: vi.fn() }))

    await waitFor(() => expect(container.querySelectorAll('.gcs-wifi-row').length).toBe(3))
    const secured = [...container.querySelectorAll('.gcs-wifi-row')]
      .find(r => r.textContent?.includes('FreeWifi_Secure'))!
    fireEvent.click(secured)

    await waitFor(() => expect(container.querySelector('.gcs-set-dialog')).toBeTruthy())
    const kb = container.querySelector('.gcs-set-kb')
    expect(kb, 'the keyboard must sit inside .gcs-set-kb, which themes paint').toBeTruthy()
    // And it must be the keyboard inside it, not an empty box.
    expect(kb!.children.length).toBeGreaterThan(0)
  })

  it('opens the password prompt empty, every time', async () => {
    // The bug this comes from, on a real box: the field still held the key
    // from an earlier attempt, the player typed the new one after it, and
    // `<old password><new password>` went to NetworkManager as one string.
    // Nothing on screen contradicted them — a masked field is dots, and twenty
    // dots look like eight from a sofa.
    //
    // Retyping is the whole flow here: the first attempt is refused, which is
    // exactly when a prompt that remembers does its damage.
    const { createWifiPage } = await load(`${SHARED}/wifi.js`)
    const { createUseSlow } = await load(`${SHARED}/slow.js`)
    const s = sdk()
    const View = createWifiPage(s, createUseSlow(s))
    const { render, waitFor, fireEvent } = await import('@testing-library/react')
    const { createElement } = await import('react')
    const { container } = render(createElement(View, { active: true, onLeave: vi.fn() }))

    // Retried rather than clicked once: the page ignores the pad and the mouse
    // while a join is in flight, so the second open lands a moment later.
    const openPrompt = async () => {
      await waitFor(() => expect(container.querySelectorAll('.gcs-wifi-row').length).toBe(3))
      await waitFor(() => {
        const row = [...container.querySelectorAll('.gcs-wifi-row')]
          .find(r => r.textContent?.includes('FreeWifi_Secure'))!
        fireEvent.click(row)
        expect(container.querySelector('.gcs-set-kb')).toBeTruthy()
      })
      return container.querySelector('.gcs-set-kb') as HTMLElement
    }
    const press = (label: string) => {
      const kb = container.querySelector('.gcs-set-kb')!
      const key = [...kb.querySelectorAll('button')].find(b => b.textContent === label)
      expect(key, `the keyboard has no "${label}" key`).toBeTruthy()
      fireEvent.click(key!)
    }

    let kb = await openPrompt()
    press('a'); press('b'); press('c')
    // The count is the only thing on a masked field that can disagree with
    // "I typed three characters".
    await waitFor(() => expect(kb.textContent).toMatch(/3 characters/))

    // And there is a way out of a field that already has something in it that
    // is not twelve presses of backspace on a d-pad.
    press('CLR')
    await waitFor(() => expect(kb.textContent).not.toMatch(/character/))
    press('a'); press('b'); press('c')

    press('↵ OK')
    await waitFor(() => expect(container.querySelector('.gcs-set-dialog')).toBeFalsy())

    kb = await openPrompt()
    expect(kb.textContent, 'the prompt reopened holding the last attempt').not.toContain('●')
    expect(kb.textContent).not.toMatch(/character/)
    expect(kb.textContent).toContain('Password')
  })
})

describe('the shared screen — Display, and its confirmation', () => {
  /** An SDK whose gamepad bus records instead of listening, so a test can ask
   *  "is anything bound to ✕ right now" — which is the whole question when a
   *  screen stops answering the pad. */
  function recordingSdk() {
    const bound = new Map<string, Set<(d?: unknown) => void>>()
    const real = sdk()
    return {
      s: {
        ...real,
        input: {
          ...real.input,
          onGp: (event: string, handler: (d?: unknown) => void) => {
            if (!bound.has(event)) bound.set(event, new Set())
            bound.get(event)!.add(handler)
            return () => bound.get(event)!.delete(handler)
          },
        },
      },
      fire: (event: string) => [...(bound.get(event) ?? [])].forEach(h => h()),
      count: (event: string) => (bound.get(event) ?? new Set()).size,
    }
  }

  async function renderDisplay(active = true) {
    const { createRows } = await load(`${SHARED}/rows.js`)
    const { createDisplayPage } = await load(`${SHARED}/display.js`)
    const { s, fire, count } = recordingSdk()
    const View = createDisplayPage(s, createRows(s))
    const { render } = await import('@testing-library/react')
    const { createElement } = await import('react')
    const r = render(createElement(View, { active, onLeave: vi.fn() }))
    return { ...r, fire, count }
  }

  it('answers the pad on the confirmation screen', async () => {
    // The bug as reported: the countdown appeared and neither stick nor buttons
    // did anything, so the only way out was to wait — on the one screen where
    // waiting is the choice you may not want.
    const { container, fire, count } = await renderDisplay()
    const { waitFor, fireEvent } = await import('@testing-library/react')

    await waitFor(() => expect(container.textContent).toMatch(/Apply this mode/))
    const apply = [...container.querySelectorAll('.gcs-row2')]
      .find(r => r.textContent?.includes('Apply this mode'))!
    fireEvent.click(apply)

    await waitFor(() => expect(container.textContent).toMatch(/Can you read this/))
    expect(count('gp:confirm'), '✕ is bound to nothing on the countdown').toBeGreaterThan(0)
    expect(count('gp:back'), '○ is bound to nothing on the countdown').toBeGreaterThan(0)

    fire('gp:confirm')
    await waitFor(() => expect(container.textContent).not.toMatch(/Can you read this/))
  })

  it('lets the cursor reach the second answer', async () => {
    // What made it feel broken: the screen looked like a list of two and the
    // cursor could not leave the first one. Pressing down did nothing, so the
    // second button read as unreachable — on the screen where choosing wrong
    // means waiting out a countdown you did not want.
    const { container, fire } = await renderDisplay()
    const { waitFor, fireEvent } = await import('@testing-library/react')

    await waitFor(() => expect(container.textContent).toMatch(/Apply this mode/))
    fireEvent.click([...container.querySelectorAll('.gcs-row2')]
      .find(r => r.textContent?.includes('Apply this mode'))!)
    await waitFor(() => expect(container.textContent).toMatch(/Can you read this/))

    const focused = () => [...container.querySelectorAll('.gcs-row2')]
      .findIndex(r => r.getAttribute('data-on') === '1')
    expect(focused()).toBe(0)

    fire('gp:dpad-down')
    await waitFor(() => expect(focused()).toBe(1))

    // And ✕ there must revert rather than keep — a cursor that moves without
    // changing what the button does is worse than no cursor at all.
    fire('gp:confirm')
    await waitFor(() => expect(container.textContent).toMatch(/previous mode/))
  })
})
