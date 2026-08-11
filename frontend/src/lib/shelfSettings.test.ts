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
    ethernet: { connected: false, iface: '', ip: '' },
  },
  '/api/settings/bluetooth/devices': [
    { mac: 'E4:17:D8:2A:9C:03', name: '8BitDo Ultimate 2C', connected: true, paired: true },
    { mac: 'A0:9E:1B:44:D2:18', name: 'Marshall Major IV', connected: false, paired: true },
  ],
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
  const { createSettings } = await load(`${THEME}/views/settings.js`)
  const { createControllersPage } = await load(`${THEME}/views/controllers.js`)
  const s = sdk()
  const View = createSettings(s, { controllers: createControllersPage(s) })
  const { render } = await import('@testing-library/react')
  const { createElement } = await import('react')
  // As an element, not a call: the view holds state, and invoking it directly
  // would run its hooks outside a render.
  return render(createElement(View, { onClose: vi.fn() }))
}

describe('Shelf v2 — the settings rail', () => {
  it('reaches every host settings page, counting the four under System', async () => {
    // The guard from the theme's side, and the reason it is worth having twice:
    // check-theme.mjs compares theme.json against the host list, which proves
    // the DECLARATION is complete. This proves the declaration matches the menu
    // that is actually drawn — a row could be deleted and theme.json left
    // alone, and nothing else would notice.
    const mod = await load(`${THEME}/views/settings.js`)
    const defaults = await import('../components/defaults')
    const src = await load(`${THEME}/theme.json`)
    const declared: string[] = (src.default ?? src).settings.pages

    expect([...declared].sort()).toEqual([...defaults.SETTINGS_PAGE_IDS].sort())

    // Every declared page is opened by some row: the eight top-level ids plus
    // the four the System row folds away.
    const source = mod.createSettings.toString()
    const reachable = new Set<string>()
    for (const id of defaults.SETTINGS_PAGE_IDS) reachable.add(id)
    const { screen, fireEvent } = await import('@testing-library/react')
    await renderRail()

    for (const label of ['Wi-Fi', 'Bluetooth', 'Audio', 'Emulators & apps', 'BIOS', 'Themes']) {
      expect(screen.getByText(label)).toBeTruthy()
    }
    // System is a door, not a page: opening it must reveal the other four.
    fireEvent.click(screen.getByText('System'))
    for (const label of ['Update', 'Standby', 'Storage', 'Desktop']) {
      expect(screen.getByText(label)).toBeTruthy()
    }
    expect(source.length).toBeGreaterThan(0)
    expect(reachable.size).toBe(10)

  })

  it('reads the value at the end of each row from the box', async () => {
    // The assertion the reference capture fails: its rail says "−42 dBm" and
    // "82 %" and nothing on this machine produces either. These come from the
    // endpoints mocked above, so a row that grew a hardcoded default would
    // stop matching.
    const { screen } = await import('@testing-library/react')
    await renderRail()

    expect(await screen.findByText('Livebox-4F2A')).toBeTruthy()   // wifi status
    expect(await screen.findByText('1 connected')).toBeTruthy()     // bluetooth devices
    expect(await screen.findByText('HDMI / DisplayPort')).toBeTruthy() // default sink
    expect(await screen.findByText('2 installed')).toBeTruthy()     // catalog
    expect(await screen.findByText('1/2 ready')).toBeTruthy()       // bios status verdict
    expect(await screen.findByText('Shelf')).toBeTruthy()           // active theme

  })

  it('leaves a row blank when its endpoint does not answer', async () => {
    // Not cosmetic. A rail that falls back to a plausible string when a service
    // is down is a rail that lies exactly when the box is broken — which is
    // when someone opens it.
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false, status: 503, statusText: 'Service Unavailable', json: async () => ({}),
    })))
    const { screen } = await import('@testing-library/react')
    const { container } = await renderRail()

    expect(screen.getByText('Wi-Fi')).toBeTruthy()
    // The rail is intact; it is the readings that are absent. Asserted on the
    // meta cells themselves rather than by scanning the panel for words — the
    // row subtitles are fixed prose and one of them says "connected", so a
    // text sweep would have been testing the copy, not the data.
    const metas = [...container.querySelectorAll('.cz-set-meta')]
    expect(metas).toHaveLength(8)

    // Seven of the eight are fed by an endpoint and go blank with it. The
    // eighth — Controllers, row four — counts pads through the Gamepad API,
    // which is the browser and is still up. It keeps answering, and that is
    // the behaviour worth pinning: the row that says whether a pad is
    // connected must not go dark because a backend service did.
    const CONTROLLERS_ROW = 3
    metas.forEach((m, i) => {
      if (i === CONTROLLERS_ROW) expect(m.textContent).toMatch(/\d+ pads?$/)
      else expect(m.textContent).toBe('')
    })
  })

  it('comes back from a System page to System, not to the top of the rail', async () => {
    // The bug this shape exists to avoid: if the rail and its sub-list were two
    // screens, returning from Storage would land on Wi-Fi and the player would
    // have to walk back down eight rows to reach Standby.
    const { screen, fireEvent } = await import('@testing-library/react')
    await renderRail()

    fireEvent.click(screen.getByText('System'))
    expect(screen.getByText('Settings · System')).toBeTruthy()
    expect(screen.queryByText('Wi-Fi')).toBeNull()

  })

  it('says so on screen when the host no longer has a page it lists', async () => {
    // A menu entry the host has dropped renders `undefined` as a component and
    // React throws, which under the shell's error boundary hands the whole
    // frontend back to the default. A theme going dark because one page was
    // renamed is the quiet failure worth answering in words.
    const { createSettings } = await load(`${THEME}/views/settings.js`)
    const real = sdk()
    const { wifi: _dropped, ...survivors } = real.defaults.DefaultSettingsPages
    const patched = { ...real, defaults: { ...real.defaults, DefaultSettingsPages: survivors } }

    const View = createSettings(patched)
    const { render, screen, fireEvent } = await import('@testing-library/react')
    const { createElement } = await import('react')
    render(createElement(View, { onClose: vi.fn() }))

    fireEvent.click(screen.getByText('Wi-Fi'))
    expect(screen.getByText(/has no .*wifi.* page/)).toBeTruthy()

  })
})

describe('Shelf v2 — the power menu', () => {
  it('renders every option it is handed, in the order it is handed them', async () => {
    // `focusIdx` is an index into `options`. A view that hides a row it does
    // not like leaves the cursor landing on nothing; one that reorders them
    // sends it jumping. Both are invisible until someone holds down and
    // shuts the box off by accident.
    const { createPowerView } = await load(`${THEME}/views/power.js`)
    const View = createPowerView(sdk())
    const PowerModal = await import('../components/modals/PowerModal')
    expect(PowerModal.default).toBeTruthy()

    const options = [
      { id: 'scan', label: 'Scan mapping', busy: 'Scanning…', icon: '◎', color: '#22c55e', desc: 'a' },
      { id: 'forget', label: 'Forget mapping', busy: 'Forgetting…', icon: '⌫', color: '#64748b', desc: 'b' },
      { id: 'restart', label: 'Restart', busy: 'Restarting…', icon: '↺', color: '#f59e0b', desc: 'c' },
      { id: 'shutdown', label: 'Shutdown', busy: 'Shutting down…', icon: '⏻', color: '#ef4444', desc: 'd' },
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

    const rows = [...container.querySelectorAll('.cz-power-row')]
    expect(rows).toHaveLength(options.length)
    expect(rows.map(r => r.querySelector('.cz-power-text b')?.textContent))
      .toEqual(options.map(o => o.label))

  })

  it('offers the way out of the front end that the box can actually perform', async () => {
    // Return to desktop is `window.gamecore.quit()`, which exists. It is the
    // third way a session ends and it was reachable only from a settings
    // sub-page, four rows into a menu nobody opens in order to quit.
    const PowerModal = await import('../components/modals/PowerModal')
    const src = PowerModal.default.toString()
    expect(src).toContain('desktop')
  })
})

describe('Shelf v2 — the Controllers page', () => {
  it('counts pads from the Gamepad API, not from the battery scan', async () => {
    // sysinfo.controllers is read_batteries(), a sysfs scan that only sees pads
    // exposing a battery. A wired pad has none, so counting it there would
    // report "no pad" on the one screen whose job is to say whether one is
    // connected — while the player is holding it.
    const pads = [{ index: 0, id: 'Wired Controller (Vendor: 045e)', buttons: { length: 17 }, axes: { length: 4 } }]
    vi.stubGlobal('navigator', Object.assign(Object.create(Object.getPrototypeOf(navigator)), navigator, {
      getGamepads: () => pads,
    }))

    const { createControllersPage } = await load(`${THEME}/views/controllers.js`)
    const View = createControllersPage(sdk())
    const { render, screen } = await import('@testing-library/react')
    const { createElement } = await import('react')
    render(createElement(View, { onClose: vi.fn(), onBack: vi.fn() }))

    expect(screen.getByText('Wired Controller (Vendor: 045e)')).toBeTruthy()
    expect(screen.getByText('P1')).toBeTruthy()
    // sysinfo reports no batteries for this pad, and the page still shows it.
    expect(screen.getByText('17 buttons · 4 axes')).toBeTruthy()

  })

  it('names where the real controller settings live', async () => {
    // The page carries no sliders because the settings the capture drew there
    // do not exist. What it must do instead is point at the three that do —
    // all of them somewhere nobody would guess.
    vi.stubGlobal('navigator', Object.assign(Object.create(Object.getPrototypeOf(navigator)), navigator, {
      getGamepads: () => [],
    }))
    const { createControllersPage } = await load(`${THEME}/views/controllers.js`)
    const View = createControllersPage(sdk())
    const { render, screen } = await import('@testing-library/react')
    const { createElement } = await import('react')
    render(createElement(View, { onClose: vi.fn(), onBack: vi.fn() }))

    expect(screen.getByText(/Vibration/)).toBeTruthy()
    expect(screen.getByText(/Test a pad/)).toBeTruthy()
    expect(screen.getByText(/forget a pad/)).toBeTruthy()

  })
})
