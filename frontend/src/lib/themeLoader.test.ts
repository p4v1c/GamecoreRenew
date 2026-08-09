/**
 * Theme loading — the gates, not the import.
 *
 * `loadTheme` ends in a runtime `import()` of a URL that only exists on a box
 * with themes installed, so what is covered here is everything that decides
 * BEFORE and AROUND that import: the SDK version gate, the stylesheet element,
 * and the two calls that talk to the backend.
 *
 * These matter because the failure mode of this file is not an exception — it
 * is a box that boots into a half-dressed UI, or into a theme it should have
 * refused.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearThemeStyles,
  fetchThemeIndex,
  loadTheme,
  resolveThemeRumble,
  resolveThemeSounds,
  setActiveTheme,
  SURFACES,
  type ThemeManifest,
} from './themeLoader'
import { SDK_VERSION } from './themeSdk'

function manifest(over: Partial<ThemeManifest> = {}): ThemeManifest {
  return {
    id: 'some-theme',
    name: 'Some Theme',
    version: '1.0.0',
    api: SDK_VERSION,
    author: 'someone',
    description: '',
    entry: 'index.js',
    preview: null,
    styles: null,
    provides: [...SURFACES],
    compatible: true,
    warnings: [],
    ...over,
  }
}

const host = {} as any

beforeEach(() => {
  document.head.innerHTML = ''
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the SDK version gate', () => {
  it('refuses a theme built against a newer SDK than this build speaks', async () => {
    // Refused at load rather than allowed to render half of itself: a theme
    // calling an SDK function this build does not have fails somewhere inside
    // a component, where the only symptom is a blank screen.
    await expect(loadTheme(manifest({ api: SDK_VERSION + 1 }), host))
      .rejects.toThrow(/SDK/)
  })

  it('accepts a theme built against an older SDK', async () => {
    // Older is fine — the SDK only grows — so this must fail on the import of
    // a theme that is not installed, never on the version check.
    await expect(loadTheme(manifest({ api: SDK_VERSION - 1 }), host))
      .rejects.not.toThrow(/SDK/)
  })
})

describe('both surfaces are mandatory', () => {
  it('names both of them, and only them', () => {
    // A theme that dresses one surface and leaves the other to the default is
    // the half-and-half UI that made the first version feel broken — a themed
    // dashboard behind the stock splash. The list is asserted so adding a
    // third surface is a deliberate change and not a silent one.
    expect(SURFACES).toEqual(['splash', 'shell'])
  })
})

describe('the theme stylesheet', () => {
  it('removes the tag when falling back to the default theme', () => {
    // A default UI still wearing the previous theme's stylesheet is the state
    // that makes a rescue look like it did nothing.
    const link = document.createElement('link')
    link.id = 'gc-theme-style'
    document.head.appendChild(link)

    clearThemeStyles()
    expect(document.getElementById('gc-theme-style')).toBeNull()
  })

  it('is a no-op when there is no stylesheet to clear', () => {
    expect(() => clearThemeStyles()).not.toThrow()
  })
})

describe('the theme sound set', () => {
  it('resolves a manifest path against the theme folder', () => {
    const [name, entry] = Object.entries(
      resolveThemeSounds(manifest({ id: 'noisy', sounds: { move: 'assets/move.wav' } })),
    )[0]
    expect(name).toBe('move')
    expect(entry).toMatch(/^\/themes\/noisy\/assets\/move\.wav\?/)
  })

  it('busts the cache the way the entry module and the stylesheet do', () => {
    // An author who edits move.wav and reloads must hear move.wav. Electron's
    // HTTP cache has hidden UI changes before, and a sound is harder to notice
    // as stale than a colour.
    const { move } = resolveThemeSounds(manifest({ sounds: { move: 'a.wav' } }))
    expect(move).toMatch(/[?&]t=\d+/)
  })

  it('lets the module override the manifest for the same name', () => {
    // Same precedence as `{ ...DefaultSettingsPages, ...ownPages }`: a theme
    // keeps the declarative form for most sounds and reaches for code on the
    // one it wants to synthesize.
    const fn = () => {}
    const out = resolveThemeSounds(
      manifest({ sounds: { move: 'assets/move.wav' } }),
      { sounds: { move: fn } },
    )
    expect(out.move).toBe(fn)
  })

  it('keeps manifest sounds the module did not mention', () => {
    const fn = () => {}
    const out = resolveThemeSounds(
      manifest({ sounds: { move: 'assets/move.wav', back: 'assets/back.wav' } }),
      { sounds: { move: fn } },
    )
    expect(out.move).toBe(fn)
    expect(out.back).toMatch(/assets\/back\.wav/)
  })

  it('accepts a plain function from a theme that synthesizes', () => {
    // Both shipped themes synthesize rather than ship audio — Summer builds its
    // surf out of filtered noise — so requiring a file to replace one bip would
    // have been a step backwards.
    const fn = () => {}
    expect(resolveThemeSounds(manifest(), { sounds: { surf: fn } }).surf).toBe(fn)
  })

  it('ignores an entry that is neither a path nor a function', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const out = resolveThemeSounds(manifest(), { sounds: { move: 42, back: null } })
    expect(out).toEqual({})
  })

  it('is empty for a theme that declares no sounds at all', () => {
    // Every theme written before this said nothing and must still sound
    // exactly as it did.
    expect(resolveThemeSounds(manifest())).toEqual({})
    expect(resolveThemeSounds(manifest(), {})).toEqual({})
  })
})

describe('the theme rumble table', () => {
  it('takes patterns keyed on gamepad events', () => {
    const out = resolveThemeRumble({ rumble: { 'gp:confirm': { duration: 40, strong: 0.5 } } })
    expect(out['gp:confirm']).toEqual({ duration: 40, strong: 0.5 })
  })

  it('accepts a sequence as readily as a single burst', () => {
    const seq = [{ duration: 20 }, { duration: 40, delay: 30 }]
    expect(resolveThemeRumble({ rumble: { 'gp:back': seq } })['gp:back']).toEqual(seq)
  })

  it('refuses to let a theme dress gp:guide', () => {
    // The core owns the double press that kills a running game, and it owns it
    // here too: a theme that could hang a three-second buzz off quitting would
    // be deciding what quitting feels like from inside the presentation layer.
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(resolveThemeRumble({ rumble: { 'gp:guide': { duration: 3000 } } })).toEqual({})
  })

  it('is empty for a theme that says nothing', () => {
    // Nothing on this box vibrated before, and a theme that did not ask for
    // haptics must not acquire them by upgrading.
    expect(resolveThemeRumble({})).toEqual({})
    expect(resolveThemeRumble({ rumble: null })).toEqual({})
    expect(resolveThemeRumble()).toEqual({})
  })

  it('drops an entry that is not a pattern', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(resolveThemeRumble({ rumble: { 'gp:confirm': 'hard' } })).toEqual({})
  })
})

describe('talking to the backend', () => {
  it('returns the index the API sends', async () => {
    const index = { sdk_version: SDK_VERSION, active: null, themes: [] }
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => index })))
    await expect(fetchThemeIndex()).resolves.toEqual(index)
  })

  it('turns a failed index into an error carrying the status', async () => {
    // The caller records this and runs the default theme whole. A silent
    // resolve here would leave it waiting for surfaces that never arrive.
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503 })))
    await expect(fetchThemeIndex()).rejects.toThrow(/503/)
  })

  it('posts the selected theme id as JSON', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    await setActiveTheme('some-theme')
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/themes/active')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ id: 'some-theme' })
  })

  it('posts a null id to go back to the default theme', async () => {
    // The rescue path. `null` has to survive the round trip as null and not
    // become the string "null", or the box asks for a theme by that name.
    const fetchMock = vi.fn(async () => ({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    await setActiveTheme(null)
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({ id: null })
  })

  it('reports a refused selection instead of resolving quietly', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500 })))
    await expect(setActiveTheme('some-theme')).rejects.toThrow(/500/)
  })
})
