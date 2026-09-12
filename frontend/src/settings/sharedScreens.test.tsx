/**
 * One layout, three surfaces — the seam, tested where it can actually break.
 *
 * The settings screen and the power menu used to live under
 * `config/themes/_shared/` and be imported by relative path from each theme.
 * They are host code now, handed to themes through `sdk.defaults`, and drawn by
 * the built-in UI directly.
 *
 * That move has exactly two failure modes, and both are silent:
 *
 *   1. The factories stop being on `sdk.defaults`. Every theme's settings
 *      screen and power menu vanish at once, and nothing else notices — the
 *      themes destructure them at build time and would throw at first render.
 *   2. The built-in screen renders, but the palette does not reach it. The
 *      colours live on `.gcs-skin-default`, a class the host passes in; drop it
 *      and the screen comes out with a theme's colours or with none.
 */
import { render, waitFor, fireEvent, act, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { buildSdk } from '../lib/themeSdk'
import * as defaults from '../components/defaults'
import SettingsScreen from '../components/modals/SettingsScreen'
import { POWER_OMIT } from '../components/DefaultShell'
// `../settings/...`, not `./...`: see index.d.ts — the ambient declarations
// match on the specifier, and it has to carry the directory name.
import { createAppsPage } from '../settings/apps'
import { createPowerView } from '../settings/power'

const sdk = () => buildSdk('shelf', { selectTheme: vi.fn(async () => {}) })

// Unmount between tests. `globals: true` is deliberately off in the vite config,
// so testing-library's automatic cleanup never runs and every tree rendered here
// stayed mounted for the rest of the file. That was invisible while each test
// only queried its own container — and stopped being invisible the moment one
// of them dispatched a `gp:*` event, which every still-mounted settings screen
// answers by switching category and rendering a page against another test's
// fetch stub.
afterEach(() => { cleanup() })

beforeEach(() => {
  // Every endpoint answers `{}` — a 200 with the wrong shape, which is what a
  // proxy, a validation error or a half-started service actually sends. This
  // is not a convenience stub: the pages here store list answers and map over
  // them, and before `asList` this exact response killed the screen with
  // "nets.map is not a function" before it drew a row. On the fallback UI there
  // is nothing behind that.
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200, statusText: 'OK', json: async () => ({}),
  })))
})

describe('the seam themes reach the shared screens through', () => {
  it('puts both factories on sdk.defaults', () => {
    // Shelf and Summer both open with `const { createSettings, createPowerView }
    // = sdk.defaults`. If these ever stop being exported, every theme's
    // settings screen and power menu break together.
    const s = sdk()
    expect(typeof (s.defaults as Record<string, unknown>).createSettings).toBe('function')
    expect(typeof (s.defaults as Record<string, unknown>).createPowerView).toBe('function')
  })

  it('is the same code the host renders, not a copy of it', () => {
    const s = sdk()
    expect((s.defaults as Record<string, unknown>).createSettings).toBe(defaults.createSettings)
    expect((s.defaults as Record<string, unknown>).createPowerView).toBe(defaults.createPowerView)
  })

  it('gives a surface no extra class when it asks for no skin', () => {
    // A theme passes no skin: its own stylesheet colours the screen from
    // `:root`, and an unasked-for class here could outrank it.
    const Screen = defaults.createSettings(sdk(), {}, {}) as React.ComponentType<{ onClose: () => void }>
    const { container } = render(<Screen onClose={() => {}} />)
    expect(container.querySelector('.gcs-set')?.className).toBe('gcs-set')
  })
})

describe('the built-in settings screen', () => {
  it('draws the rail, not the old list of ten rows', async () => {
    const { container } = render(<SettingsScreen onClose={() => {}} />)
    // Scoped to the rail on purpose: "Wi-Fi" is also the heading of the page
    // beside it, and a query over the whole screen would match either and
    // prove neither.
    const rail = () => container.querySelector('.gcs-set-rail')
    await waitFor(() => expect(rail()).toBeTruthy())
    const rows = [...rail()!.querySelectorAll('.gcs-set-row')].map(r => r.textContent ?? '')
    // The capture's nine, in its order. The list this replaced had Storage,
    // Standby and Update as top-level rows; the rail folds them into System,
    // which is the difference that matters.
    for (const label of ['Wi-Fi', 'Bluetooth', 'Display', 'Audio', 'Controllers',
                         'Applications', 'BIOS', 'Themes', 'System']) {
      expect(rows.some(r => r.includes(label)), `${label} is missing from the rail`).toBe(true)
    }
    expect(rows).toHaveLength(9)
  })

  it('carries the class its palette is scoped to', () => {
    // Without this the screen renders in whatever colours happen to be loaded —
    // including a theme's, when safe mode swaps just this surface back.
    const { container } = render(<SettingsScreen onClose={() => {}} />)
    expect(container.querySelector('.gcs-set.gcs-skin-default')).toBeTruthy()
  })

  it('opens even when nothing on the box answers', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('no box') }))
    const { container } = render(<SettingsScreen onClose={() => {}} />)
    // Same rule as the list it replaced: a settings screen that fails to open
    // because a service is down is the last thing this surface may do.
    await waitFor(() =>
      expect(container.querySelectorAll('.gcs-set-rail .gcs-set-row')).toHaveLength(9))
  })
})

describe('the applications page', () => {
  /** Two apps and an emulator: the emulator is the assertion, not scenery. */
  const CATALOGUE = [
    { id: 'steam', kind: 'app', label: 'Steam', family: '', color: '#123456',
      emulatorName: 'Steam', description: 'Big Picture', installed: true,
      logo: 'assets/logos/steam.png', origin: 'shipped', restricted: [] },
    { id: 'youtube', kind: 'app', label: 'YouTube', family: '', color: '#abcdef',
      emulatorName: '', description: '', installed: false,
      logo: null, origin: 'shipped', restricted: [] },
    { id: 'dolphin', kind: 'emulator', label: 'GameCube / Wii', family: 'Nintendo',
      color: '#6C4FD6', emulatorName: 'Dolphin', description: '', installed: true,
      logo: 'assets/logos/dolphin.png', origin: 'shipped', restricted: [] },
  ]

  const mount = async (rows: unknown[] = CATALOGUE) => {
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) =>
      ({ ok: true, status: 200, statusText: 'OK',
         json: async () => (String(url).endsWith('/api/catalog') ? rows : {}) })))
    const Page = createAppsPage(sdk()) as React.ComponentType<{ active: boolean; onLeave: () => void }>
    const { container } = render(<Page active onLeave={() => {}} />)
    await waitFor(() => expect(container.querySelector('.gcs-pack')).toBeTruthy())
    return container
  }

  const packs = (c: HTMLElement) => [...c.querySelectorAll('.gcs-pack')] as HTMLElement[]
  const button = (row: HTMLElement) => row.querySelector('.gcs-pack-btn')?.textContent?.trim()

  it('lists the applications and not the consoles', async () => {
    // The whole point of the split. This page used to show all thirty-five
    // packs behind an accordion of makers; the consoles are the Store's now,
    // and a page still offering to install Dolphin would be two screens
    // racing the one backend lock.
    const c = await mount()
    expect(packs(c)).toHaveLength(2)
    expect(c.textContent).toContain('Steam')
    expect(c.textContent).toContain('YouTube')
    expect(c.textContent).not.toContain('GameCube')
    // …and it is a flat list: no group headers left to unfold.
    expect(c.querySelectorAll('.gcs-grp')).toHaveLength(0)
  })

  it('counts only the applications in its heading', async () => {
    const c = await mount()
    // Not "2/3": the emulator in the answer belongs to another screen, and a
    // heading that counted it would be reporting on packs this page cannot
    // touch.
    expect(c.querySelector('.gcs-wifi-state')?.textContent).toBe('1/2 INSTALLED')
  })

  it("draws each pack's own logo, and keeps the swatch for one with none", async () => {
    const c = await mount()
    // Absolute, because the row is rendered inside a settings screen that has
    // no base path of its own — a relative `assets/...` would resolve against
    // whatever route the front end happens to be on.
    expect([...c.querySelectorAll('img')].map(i => i.getAttribute('src')))
      .toEqual(['/assets/logos/steam.png'])
    // The swatch is still the honest answer when there is no artwork: no image
    // request, no broken-image glyph, the colour the pack declares.
    const dots = [...c.querySelectorAll('.gcs-pack-dot')] as HTMLElement[]
    expect(dots[1].getAttribute('data-logo')).toBeNull()
    expect(dots[1].style.background).toBe('rgb(171, 205, 239)')   // #abcdef
  })

  it('asks twice before it removes something', async () => {
    // This page removed on ONE press of ✕, on whatever row the cursor happened
    // to be sitting, for as long as it existed. The arm-then-confirm rule lives
    // in `useCatalog` now, so it arrived here with the shared hook.
    const c = await mount()
    const posts = () => vi.mocked(fetch).mock.calls
      .filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')

    fireEvent.click(packs(c)[0])                       // Steam, installed
    await waitFor(() => expect(button(packs(c)[0])).toBe('Confirm?'))
    expect(posts()).toHaveLength(0)

    fireEvent.click(packs(c)[0])
    await waitFor(() => expect(posts()).toHaveLength(1))
    expect(String(posts()[0][0])).toContain('/catalog/steam/remove')
  })

  it('installs on the first press, because installing is not destructive', async () => {
    const c = await mount()
    fireEvent.click(packs(c)[1])                       // YouTube, not installed
    await waitFor(() => {
      const posts = vi.mocked(fetch).mock.calls
        .filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
      expect(posts).toHaveLength(1)
      expect(String(posts[0][0])).toContain('/catalog/youtube/install')
    })
  })

  it('says so rather than drawing an empty list when there are no apps', async () => {
    // A box whose only packs are consoles. Not an empty panel: an empty panel
    // reads as a page that failed to load, which is the sentence this screen
    // may least afford to say by accident.
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) =>
      ({ ok: true, status: 200, statusText: 'OK',
         json: async () => (String(url).endsWith('/api/catalog') ? [CATALOGUE[2]] : {}) })))
    const Page = createAppsPage(sdk()) as React.ComponentType<{ active: boolean; onLeave: () => void }>
    const { container } = render(<Page active onLeave={() => {}} />)
    await waitFor(() =>
      expect(container.textContent).toContain('No application packs are installed'))
    expect(container.querySelectorAll('.gcs-pack')).toHaveLength(0)
  })
})

describe('the built-in power menu', () => {
  const render3 = (omit?: string[]) => {
    const View = createPowerView(sdk(), {}) as React.ComponentType<Record<string, unknown>>
    const options = [
      { id: 'scan', label: 'Scan mapping', busy: '', color: '#22c55e', desc: '' },
      { id: 'forget', label: 'Forget mapping', busy: '', color: '#64748b', desc: '' },
      { id: 'shutdown', label: 'Shutdown', busy: '', color: '#ef4444', desc: '' },
      { id: 'restart', label: 'Restart', busy: '', color: '#f59e0b', desc: '' },
      { id: 'desktop', label: 'Return to desktop', busy: '', color: '#38bdf8', desc: '' },
    ].filter(o => !(omit ?? []).includes(o.id))
    const { container } = render(
      <View options={options} focusIdx={0} confirmId={null} pendingId={null}
        scanning={false} scanResult={null} onFocus={() => {}} onActivate={() => {}}
        onCancel={() => {}} />)
    return [...container.querySelectorAll('.gcs-pwr-row b')].map(b => b.textContent)
  }

  it('omits the two mapping rows by default', () => {
    // They were here because this modal had the two-press confirmation and no
    // settings screen did. The built-in settings screen has a Controllers page
    // now — the same rail both themes draw — so the reason is gone and this is
    // the three ways a session ends.
    expect(render3(POWER_OMIT)).toEqual(['Shutdown', 'Restart', 'Return to desktop'])
  })

  it('still shows them to a surface that asks for the full menu', () => {
    // `parts.powerOmit ?? POWER_OMIT` in DefaultShell: an explicit empty array
    // is a request, not an absent value, and `||` would have swallowed it.
    expect(render3([])).toHaveLength(5)
    expect(render3([])).toContain('Scan mapping')
  })
})

describe('the applications list, walked with the pad', () => {
  const CATALOGUE = [
    { id: 'steam', kind: 'app', label: 'Steam', family: '', color: '#a',
      emulatorName: 'Steam', description: '', installed: true,
      logo: 'assets/logos/steam.png', origin: 'shipped', restricted: [] },
    { id: 'stremio', kind: 'app', label: 'Stremio', family: '', color: '#b',
      emulatorName: 'Stremio', description: '', installed: false,
      logo: 'assets/logos/stremio.png', origin: 'shipped', restricted: [] },
    { id: 'youtube', kind: 'app', label: 'YouTube', family: '', color: '#c',
      emulatorName: 'YouTube', description: '', installed: false,
      logo: 'assets/logos/youtube.png', origin: 'shipped', restricted: [] },
  ]

  const mount = async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) =>
      ({ ok: true, status: 200, statusText: 'OK',
         json: async () => (String(url).endsWith('/api/catalog') ? CATALOGUE : {}) })))
    const Page = createAppsPage(sdk()) as React.ComponentType<{ active: boolean; onLeave: () => void }>
    const { container } = render(<Page active onLeave={() => {}} />)
    await waitFor(() => expect(container.querySelectorAll('.gcs-pack').length).toBe(3))
    return container
  }

  const packs = (c: HTMLElement) => [...c.querySelectorAll('.gcs-pack')] as HTMLElement[]
  const focused = (c: HTMLElement) =>
    packs(c).find(e => e.getAttribute('data-on') === '1')
  const press = (event: string) =>
    act(() => { window.dispatchEvent(new CustomEvent(event)) })

  it('opens on the first row, with nothing folded away', async () => {
    // The accordion this replaced opened with every group shut, which was the
    // right answer for twenty systems behind five makers. Three applications
    // are not a wall, and a fold in front of them would be one press between
    // the player and everything on the page.
    const c = await mount()
    expect(focused(c)).toBe(packs(c)[0])
    expect(c.querySelectorAll('.gcs-grp')).toHaveLength(0)
  })

  it('walks the rows on the d-pad and wraps at the end', async () => {
    const c = await mount()
    press('gp:dpad-down')
    await waitFor(() => expect(focused(c)).toBe(packs(c)[1]))
    press('gp:dpad-up')
    await waitFor(() => expect(focused(c)).toBe(packs(c)[0]))
    press('gp:dpad-up')
    await waitFor(() => expect(focused(c)).toBe(packs(c)[2]))
  })

  it('disarms a removal when the cursor steps away', async () => {
    const c = await mount()
    press('gp:confirm')                                  // Steam, installed
    await waitFor(() => expect(c.textContent).toContain('Confirm?'))
    press('gp:dpad-down')
    await waitFor(() => expect(c.textContent).not.toContain('Confirm?'))
    // …and the step really did cancel it, rather than only stop saying so.
    const posts = vi.mocked(fetch).mock.calls
      .filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
    expect(posts).toHaveLength(0)
  })

  it('leaves on ○ and on ←, the way every page on this rail does', async () => {
    const onLeave = vi.fn()
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) =>
      ({ ok: true, status: 200, statusText: 'OK',
         json: async () => (String(url).endsWith('/api/catalog') ? CATALOGUE : {}) })))
    const Page = createAppsPage(sdk()) as React.ComponentType<{ active: boolean; onLeave: () => void }>
    render(<Page active onLeave={onLeave} />)
    await waitFor(() => expect(onLeave).not.toHaveBeenCalled())
    press('gp:back')
    press('gp:dpad-left')
    expect(onLeave).toHaveBeenCalledTimes(2)
  })
})
