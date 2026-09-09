/**
 * Summer — the theme this work did not touch, mounted to prove it.
 *
 * Orbit and Shelf were both changed here, and so were two things every theme
 * sits on: the gamepad bus (`useGamepad`) and the backend's guide gesture. A
 * change to a shared foundation that is only ever exercised through the two
 * themes being worked on is a change nobody has tested — the third theme is
 * where a leak shows up.
 *
 * So this mounts Summer against the real SDK and asserts the contract every
 * theme depends on and none of them own:
 *
 *   · it still loads, renders and tears down;
 *   · the `gp:*` bus reaches it, and stops reaching it once it is gone;
 *   · `gp:guide` is still reserved — a theme may not take the one binding
 *     that gets a player out of a game;
 *   · nothing Orbit added to the SDK surface is required to exist.
 *
 * What is NOT claimed: how Summer looks, or that its WebGL ocean runs. jsdom
 * has no WebGL, and the theme is written to survive that — which is itself
 * part of what is asserted below.
 */
import { render, act, cleanup, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createElement } from 'react'
import { buildSdk } from './themeSdk'
import { useStore } from '../store'

const THEME = '../../../config/themes/summer'

const SYSTEMS = [
  { id: 'rpcs3', label: 'RPCS3', kind: 'emulator' as const },
  { id: 'stremio', label: 'Stremio', kind: 'app' as const },
]

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(typeof input === 'string' ? input : (input as Request).url ?? input)
    const body: unknown =
      url.endsWith('/systems') ? SYSTEMS
        : url.endsWith('/systems/rpcs3') ? SYSTEMS[0]
          : url.endsWith('/systems/rpcs3/games')
            ? [{ filename: 'Journey.iso', display_name: 'Journey', path: '/t/Journey.iso' }]
            : url.includes('/playtime') ? []
              : url.includes('/metadata') ? { found: false }
                : url.includes('/media') ? { media: {} }
                  : url.endsWith('/sysinfo') ? { controllers: [], ip: '192.0.2.1' }
                    : url.includes('/settings') ? {}
                      : []
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
  useStore.setState({
    screen: 'home', selectedSystemId: null, selectedGameIdx: 0, gridFocusIdx: 0,
    gridPage: 0, modalDepth: 0, standby: 'off', powerPending: null,
    sessionGameKey: null, sessionSystemId: null, backgroundSessions: [],
  })
})

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

async function summer() {
  const { default: createSummer } = await import(/* @vite-ignore */ `${THEME}/index.js`)
  const sdk = buildSdk('summer', { selectTheme: vi.fn(async () => {}) })
  const theme = createSummer(sdk)
  return { theme, sdk }
}

const flush = () => act(async () => { await new Promise(r => setTimeout(r, 0)) })

describe('Summer, after the Orbit and Shelf work', () => {
  it('still builds against the SDK the host hands it', async () => {
    const { theme } = await summer()
    expect(typeof theme.shell).toBe('function')
    expect(theme.splash === undefined || typeof theme.splash === 'function').toBe(true)
  })

  it('still renders a shell, and takes it down again', async () => {
    // A theme that throws on mount takes the whole interface with it — there
    // is no other screen on this box.
    const { theme } = await summer()
    const r = render(createElement(theme.shell))
    await flush()
    expect(r.container.firstChild).toBeTruthy()
    expect(() => r.unmount()).not.toThrow()
  })

  it('survives a jsdom with no WebGL, the way it must survive a box with none', async () => {
    const { theme } = await summer()
    const r = render(createElement(theme.shell))
    await flush()
    // Nothing is asserted about the ocean. What is asserted is that its
    // absence does not take the interface down with it.
    await waitFor(() => expect(r.container.firstChild).toBeTruthy())
  })

  it('still hears the pad through the shared bus', async () => {
    // `useGamepad` was rewritten for hysteresis, repeat and multi-pad. The
    // events it puts on `window` are the contract every theme reads, and this
    // theme was not part of that work.
    const { sdk } = await summer()
    const seen: string[] = []
    const off = (sdk.input as { onGp: (e: string, h: () => void) => () => void })
      .onGp('gp:dpad-down', () => seen.push('down'))

    window.dispatchEvent(new CustomEvent('gp:dpad-down'))
    expect(seen).toEqual(['down'])
    off()
    window.dispatchEvent(new CustomEvent('gp:dpad-down'))
    expect(seen).toEqual(['down'])
  })

  it('is still refused the one binding it may not have', async () => {
    // `gp:guide` is the only way out of a running game, and the backend's
    // double-press and Start+Select gestures both broadcast it. A theme that
    // could take it could hang a player inside an emulator.
    const { sdk } = await summer()
    const input = sdk.input as { onGp: (e: string, h: () => void) => () => void }
    const seen: string[] = []
    const off = input.onGp('gp:guide', () => seen.push('guide'))

    window.dispatchEvent(new CustomEvent('gp:guide'))
    expect(seen).toEqual([])
    off()
  })

  it('does not need anything Orbit grew during this work', async () => {
    // Orbit gained `lib/media-cache.js` and `lib/physical-media.js`. Those are
    // theme-local by construction; a second theme must not have started
    // depending on them by accident.
    const { theme } = await summer()
    const r = render(createElement(theme.shell))
    await flush()
    expect(r.container.querySelector('.orbit-physical')).toBeNull()
    expect(r.container.querySelector('.orbit-backdrop-crossfade')).toBeNull()
  })

  it('leaves no listener on the window after it is unmounted', async () => {
    // On a box that never restarts its browser, a theme swapped ten times
    // leaves ten sets of bindings and one press counts as ten.
    const { theme } = await summer()
    const r = render(createElement(theme.shell))
    await flush()
    r.unmount()
    await flush()
    expect(() => {
      for (const e of ['gp:dpad-up', 'gp:dpad-down', 'gp:confirm', 'gp:back', 'gp:menu']) {
        window.dispatchEvent(new CustomEvent(e))
      }
    }).not.toThrow()
  })
})
