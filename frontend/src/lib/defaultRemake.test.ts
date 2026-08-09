/**
 * The acceptance test, run as a test.
 *
 * `config/themes/default-remake` is the default UI rebuilt as an ordinary
 * third-party theme. Its whole purpose is to fail when the SDK stops being able
 * to express the default frontend — so it is worth actually running, against
 * the real `buildSdk()` output rather than a stub.
 *
 * A stub would defeat the point twice over: it would pass when the SDK lost a
 * key the theme needs, and it would need updating by the same person who just
 * removed that key.
 *
 * The theme is imported through a variable path so `tsc` treats it as dynamic —
 * `npm run build` typechecks this file, and these are plain .js modules with no
 * declarations.
 */
import { describe, expect, it, vi } from 'vitest'
import { buildSdk } from './themeSdk'

const THEME = '../../../config/themes/default-remake'

/** The real SDK, as the loader hands it to a theme. */
const sdk = () => buildSdk('default-remake', { selectTheme: vi.fn(async () => {}) })

async function load(path: string) {
  return await import(/* @vite-ignore */ path)
}

describe('the default-remake theme', () => {
  it('produces both surfaces from the real SDK', async () => {
    const mod = await load(`${THEME}/index.js`)
    const produced = mod.default(sdk())

    // Both, always. A theme that dresses one and leaves the other to the
    // default is the half-and-half UI the all-or-nothing rule exists to stop.
    expect(typeof produced.splash).toBe('function')
    expect(typeof produced.shell).toBe('function')
  })

  it('declares no sounds and no rumble, like the UI it remakes', async () => {
    // Not an omission — it is the assertion. The default UI uses the host's
    // five synthesized sounds and vibrates nothing, so a faithful remake
    // declares neither, and every run exercises the fallback end of both
    // cascades.
    const mod = await load(`${THEME}/index.js`)
    const produced = mod.default(sdk())
    expect(produced.sounds).toBeUndefined()
    expect(produced.rumble).toBeUndefined()
  })

  it('renders its dashboard from a synthetic roster', async () => {
    // The view that found the first hole. It reads sdk.format.systemColor,
    // .time and .date; losing any of them throws here rather than silently
    // painting a dashboard the wrong colour on somebody's TV.
    const { createHomeView } = await load(`${THEME}/views/home.js`)
    const View = createHomeView(sdk())

    const systems = [
      { id: 'rpcs3', kind: 'emulator', label: 'PlayStation 3' },
      // No colour, which is the case a theme gets wrong: `color` is optional
      // and this system must still not come out the house purple by accident.
      { id: 'dolphin', kind: 'emulator', label: 'GameCube' },
    ]
    const el = View({
      systems,
      pageItems: systems,
      playtime: { rpcs3: { total_secs: 7200, last_played: '2026-01-02T10:00:00' } },
      counts: { rpcs3: 12, dolphin: 3 },
      focusIdx: 0, page: 0, pageCount: 1, cols: 4, rows: 2, perPage: 8,
      totals: { systems: 2, games: 15, hours: 2 },
      onFocus: vi.fn(), onPage: vi.fn(), onActivate: vi.fn(),
    })

    expect(el).toBeTruthy()

    const { render, screen, cleanup } = await import('@testing-library/react')
    render(el)
    expect(screen.getByText('PlayStation 3')).toBeTruthy()
    expect(screen.getByText('GameCube')).toBeTruthy()
    expect(screen.getByText('12 games')).toBeTruthy()
    cleanup()
  })

  it('resolves every settings page its menu lists', async () => {
    // The guard, from the theme's side. A menu entry the host cannot resolve
    // renders nothing when selected — the page exists, the route exists, and
    // pressing ✕ does nothing at all.
    const { createSettings } = await load(`${THEME}/views/settings.js`)
    const defaults = await import('../components/defaults')

    // Read the ids the theme's own menu declares rather than restating them.
    const src = await load(`${THEME}/theme.json`)
    const declared: string[] = (src.default ?? src).settings.pages

    expect(typeof createSettings).toBe('function')
    for (const id of declared) {
      expect(defaults.DefaultSettingsPages).toHaveProperty(id)
    }
    // And the other direction: nothing the host offers is missing from it.
    expect([...declared].sort()).toEqual([...defaults.SETTINGS_PAGE_IDS].sort())
  })

  it('says so on screen when the host no longer has a page it lists', async () => {
    // The branch the test above can never reach, because every entry resolves
    // today. It is the interesting one: a menu entry the host has dropped
    // renders `undefined` as a component, and React throws — which under the
    // shell's error boundary hands the whole frontend back to the default. A
    // theme going dark because one page was renamed is precisely the quiet
    // failure this phase exists to stop, so the remake answers it in words.
    const { createSettings } = await load(`${THEME}/views/settings.js`)

    const real = sdk()
    // Spread rather than mutate: DefaultSettingsPages is shared module state,
    // and deleting from it would break whichever test ran next.
    const { wifi: _dropped, ...survivors } = real.defaults.DefaultSettingsPages
    const patched = {
      ...real,
      defaults: { ...real.defaults, DefaultSettingsPages: survivors },
    }

    const View = createSettings(patched)
    const { render, screen, fireEvent, cleanup } = await import('@testing-library/react')
    const { createElement } = await import('react')
    // As an element, not a call: this view holds state, and invoking it
    // directly would run its hooks outside a render.
    render(createElement(View, { onClose: vi.fn() }))

    fireEvent.click(screen.getByText('Wi-Fi'))

    expect(screen.getByText(/has no .*wifi.* page/)).toBeTruthy()
    cleanup()
  })
})
