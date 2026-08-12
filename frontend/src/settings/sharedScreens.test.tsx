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
import { render, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { buildSdk } from '../lib/themeSdk'
import * as defaults from '../components/defaults'
import SettingsScreen from '../components/modals/SettingsScreen'
import { POWER_OMIT } from '../components/DefaultShell'
// `../settings/...`, not `./...`: see index.d.ts — the ambient declarations
// match on the specifier, and it has to carry the directory name.
import { createCatalogPage } from '../settings/catalog'
import { createPowerView } from '../settings/power'

const sdk = () => buildSdk('shelf', { selectTheme: vi.fn(async () => {}) })

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
                         'Emulators & apps', 'BIOS', 'Themes', 'System']) {
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

describe('the catalogue page', () => {
  it('draws each pack\'s own logo, not a colour swatch', async () => {
    const packs = [
      { id: 'dolphin', label: 'GameCube / Wii', family: 'Nintendo', color: '#6C4FD6',
        emulatorName: 'Dolphin', installed: true, logo: 'assets/logos/dolphin.png' },
      // Same family on purpose: the page opens the first maker group and
      // leaves the rest shut, so a second family would be collapsed and this
      // would be asserting on a row nobody rendered.
      { id: 'melonds', label: 'Nintendo DS', family: 'Nintendo', color: '#8B8992',
        emulatorName: 'melonDS', installed: false, logo: 'assets/logos/melonds.png' },
    ]
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) =>
      ({ ok: true, status: 200, statusText: 'OK',
         json: async () => (String(url).endsWith('/api/catalog') ? packs : {}) })))

    const Page = createCatalogPage(sdk()) as React.ComponentType<{ active: boolean; onLeave: () => void }>
    const { container } = render(<Page active onLeave={() => {}} />)

    await waitFor(() => expect(container.querySelectorAll('img').length).toBe(2))
    // Absolute, because the row is rendered inside a settings screen that has
    // no base path of its own — a relative `assets/...` would resolve against
    // whatever route the front end happens to be on.
    expect([...container.querySelectorAll('img')].map(i => i.getAttribute('src')))
      .toEqual(['/assets/logos/dolphin.png', '/assets/logos/melonds.png'])
  })

  it('keeps the colour swatch for a pack that ships no logo', async () => {
    const packs = [{ id: 'nologo', label: 'Something', family: 'Other', color: '#123456',
                     emulatorName: '', installed: false, logo: null }]
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) =>
      ({ ok: true, status: 200, statusText: 'OK',
         json: async () => (String(url).endsWith('/api/catalog') ? packs : {}) })))

    const Page = createCatalogPage(sdk()) as React.ComponentType<{ active: boolean; onLeave: () => void }>
    const { container } = render(<Page active onLeave={() => {}} />)

    // The swatch is what this screen showed for every row before, and it is
    // still the honest answer when there is no artwork: no image request, no
    // broken-image glyph, the colour the pack declares.
    await waitFor(() => expect(container.querySelector('.gcs-pack-dot')).toBeTruthy())
    expect(container.querySelector('img')).toBeNull()
    const dot = container.querySelector('.gcs-pack-dot') as HTMLElement
    expect(dot.getAttribute('data-logo')).toBeNull()
    expect(dot.style.background).toBe('rgb(18, 52, 86)')   // #123456
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
