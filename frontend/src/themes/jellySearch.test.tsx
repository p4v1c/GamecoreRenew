/**
 * Jelly's search, its details panel, its session parts and its settings,
 * against the real SDK. The search is a layer Jelly opens itself, so the
 * claims here are the ones the brief makes: the pad starts on A, three zones,
 * the cursor never jumps on a keystroke, ○ goes back to the keyboard and then
 * closes, a details panel returns to the result it came from, and the modal
 * depth is given back.
 *
 * jsdom has no layout, so d-pad steps between keys are walked in a browser
 * (see the theme README); here the focused control is set, and every button
 * press goes through the real gp:* handlers.
 */
import { render, act, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React, { createElement } from 'react'
import { buildSdk } from '../lib/themeSdk'
import { useStore } from '../store'
import HomeScreen from '../components/HomeScreen'

const THEME = '../../../config/themes/jelly'

const SYSTEMS = [
  { id: 'azahar', label: 'Azahar', kind: 'emulator' as const },
  { id: 'gopher64', label: 'Gopher64', kind: 'emulator' as const },
  { id: 'snes9x', label: 'Snes9x', kind: 'emulator' as const },
]
const GAMES: Record<string, unknown[]> = {
  azahar: [
    { filename: 'Mario Kart 7.3ds', display_name: 'Mario Kart 7', path: '/r/mk7.3ds' },
    { filename: 'Pokemon X.3ds', display_name: 'Pokémon X', path: '/r/px.3ds' },
  ],
  gopher64: [{ filename: 'Super Mario 64.z64', display_name: 'Super Mario 64', path: '/r/sm64.z64' }],
  snes9x: [{ filename: 'Chrono Trigger.sfc', display_name: 'Chrono Trigger', path: '/r/ct.sfc' }],
}

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(typeof input === 'string' ? input : (input as Request).url ?? input)
    const games = url.match(/\/systems\/([^/]+)\/games/)
    const body: unknown = games ? (GAMES[decodeURIComponent(games[1])] ?? [])
      : url.endsWith('/systems') ? SYSTEMS
        : url.includes('/metadata') ? { found: false }
          : url.includes('/sysinfo') ? { controllers: [] } : []
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
  useStore.setState({
    screen: 'home', selectedSystemId: null, gridFocusIdx: 0, gridPage: 0, modalDepth: 0,
    sessionGameKey: null, sessionSystemId: null, transition: null, backgroundSessions: [],
    powerPending: null, standby: 'off',
  })
})

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const settle = () => act(async () => { for (let i = 0; i < 4; i++) await new Promise(r => setTimeout(r, 0)) })
const press = async (event: string, n = 1) => {
  await act(async () => {
    for (let i = 0; i < n; i++) window.dispatchEvent(new CustomEvent(event))
    await new Promise(r => setTimeout(r, 0))
  })
}
const focused = () => (document.activeElement as HTMLElement | null)?.dataset?.nav
const query = () => document.querySelector('.jl-query-text')?.textContent
const titles = () => [...document.querySelectorAll('.jl-result b')].map(e => e.textContent)
/** Put the pad on a key, then press ✕ through the real handler. */
const typeKey = async (k: string) => {
  ;(document.querySelector(`[data-nav="k-${k}"]`) as HTMLElement).focus()
  await press('gp:confirm')
}

async function home() {
  const sdk = buildSdk('jelly', { selectTheme: vi.fn(async () => {}) })
  const launchGame = vi.fn(async () => {})
  ;(sdk.defaults as Record<string, unknown>).launchGame = launchGame
  const mod = await import(/* @vite-ignore */ `${THEME}/index.js`)
  const View = mod.createParts(sdk).Home
  const r = render(createElement(HomeScreen as unknown as React.ComponentType<Record<string, unknown>>,
    { view: View, omit: ['nav', 'pages', 'confirm'], onLaunchApp: vi.fn() }))
  await settle()
  return { ...r, sdk, launchGame }
}

describe('the search', () => {
  it('opens on △ with the pad on A, never on a text field', async () => {
    await home()
    await press('gp:y')
    expect(document.querySelector('.jl-search')).toBeTruthy()
    expect(focused()).toBe('k-A')
    expect(document.querySelector('.jl-search input')).toBeNull()
    expect(useStore.getState().modalDepth).toBe(1)
  })

  it('types MARIO on the virtual keyboard and filters as it goes', async () => {
    await home()
    await press('gp:y')
    for (const k of ['M', 'A', 'R', 'I', 'O']) await typeKey(k)
    expect(query()).toBe('MARIO')
    expect(titles().sort()).toEqual(['Mario Kart 7', 'Super Mario 64'])
    // The cursor stayed on the last key typed: a keystroke never moves it.
    expect(focused()).toBe('k-O')
  })

  it('ignores accents, and □ erases while L2 clears everything', async () => {
    await home()
    await press('gp:y')
    for (const k of ['P', 'O', 'K', 'E']) await typeKey(k)
    expect(titles()).toEqual(['Pokémon X'])
    await press('gp:x')
    expect(query()).toBe('POK')
    await press('gp:l2')
    expect(query()).toBe('A game, a console…')
    expect(titles()).toHaveLength(4)
  })

  it('walks Keyboard → Filters → Games with R1, and filters by console', async () => {
    await home()
    await press('gp:y')
    await press('gp:r1')
    expect(focused()).toBe('sf-all')
    ;(document.querySelector('[data-nav="sf-gopher64"]') as HTMLElement).focus()
    await press('gp:confirm')
    expect(titles()).toEqual(['Super Mario 64'])
    await press('gp:r1')
    expect(focused()).toBe('r-gopher64:Super Mario 64.z64')
    await press('gp:l1', 2)
    expect(focused()).toBe('k-A')
  })

  it('△ jumps between the keyboard and the results, remembering both', async () => {
    await home()
    await press('gp:y')
    await typeKey('O')
    await press('gp:y')
    const firstResult = focused()
    expect(firstResult?.startsWith('r-')).toBe(true)
    const second = document.querySelectorAll('.jl-result')[1] as HTMLElement
    second.focus()
    await press('gp:y')
    expect(focused()).toBe('k-O')
    await press('gp:y')
    expect(focused()).toBe(second.dataset.nav)
  })

  it('opens the details panel from a result and comes back to that same result', async () => {
    const { launchGame } = await home()
    await press('gp:y')
    await press('gp:y')
    const result = document.querySelectorAll('.jl-result')[2] as HTMLElement
    result.focus()
    await press('gp:confirm')
    await settle()
    expect(document.querySelector('.jl-details')).toBeTruthy()
    expect(focused()).toBe('play')
    expect(useStore.getState().modalDepth).toBe(2)
    await press('gp:back')
    expect(document.querySelector('.jl-details')).toBeNull()
    expect(focused()).toBe(result.dataset.nav)
    // The details panel's Play launches the real ROM.
    await press('gp:confirm')
    await settle()
    ;(document.querySelector('[data-nav="play"]') as HTMLElement).focus()
    await press('gp:confirm')
    await settle()
    expect(launchGame).toHaveBeenCalledTimes(1)
  })

  it('○ goes back to the keyboard, then closes and gives the pad back', async () => {
    await home()
    await press('gp:y')
    await press('gp:r1', 2)
    await press('gp:back')
    expect(focused()).toBe('k-A')
    expect(document.querySelector('.jl-search')).toBeTruthy()
    await press('gp:back')
    expect(document.querySelector('.jl-search')).toBeNull()
    expect(useStore.getState().modalDepth).toBe(0)
    // And the dashboard has its cursor again.
    expect(focused()).toBe('hero-play')
  })
})

describe('the details panel', () => {
  it('toggles a favourite with △ and says so', async () => {
    await home()
    ;(document.querySelector('[data-nav="hero-details"]') as HTMLElement).focus()
    await press('gp:confirm')
    await settle()
    await press('gp:y')
    expect(document.querySelector('[data-nav="fav"]')?.textContent).toContain('Remove from favourites')
    expect(JSON.parse(localStorage.getItem('jelly-favourites') || '[]')).toHaveLength(1)
  })
})

describe('the session parts', () => {
  const load = async () => {
    const sdk = buildSdk('jelly', { selectTheme: vi.fn(async () => {}) })
    const mod = await import(/* @vite-ignore */ `${THEME}/index.js`)
    return mod.createParts(sdk).session
  }

  it('the menu draws the host\'s actions and marks the one the pad is on', async () => {
    const { Menu } = await load()
    const run = vi.fn()
    const s = { session: 3, gameKey: 'youtube', systemId: 'youtube', kind: 'app' }
    const r = render(createElement(Menu, {
      session: s, sessions: [s], index: 0, confirming: false, busy: false, actionIdx: 1,
      title: () => 'YouTube',
      actions: [{ id: 'resume', label: 'Resume', primary: true, run }, { id: 'close', label: 'Close', danger: true, run }],
    }))
    const options = r.container.querySelectorAll('.jl-session-option')
    expect(options[1].getAttribute('data-active')).toBe('true')
    expect(r.container.textContent).toContain('App paused')
    ;(options[0] as HTMLElement).click()
    expect(run).toHaveBeenCalled()
  })

  it('the bar binds no button and points at PS ×2', async () => {
    const { Bar } = await load()
    const onManage = vi.fn()
    const s = { session: 1, gameKey: 'Zelda_(USA).iso', systemId: 'dolphin', kind: 'game' }
    const r = render(createElement(Bar, { sessions: [s], focusIdx: 0, active: true, busy: false, onManage }))
    expect(r.container.querySelector('.jl-dock-text b')?.textContent).toBe('Zelda')
    ;(r.container.querySelector('.jl-dock-button') as HTMLElement).click()
    expect(onManage).toHaveBeenCalledTimes(1)
  })
})

describe('the settings', () => {
  it('is the host\'s ten-category screen, with L1/R1 between categories', async () => {
    const sdk = buildSdk('jelly', { selectTheme: vi.fn(async () => {}) })
    const { createJellySettings } = await import(/* @vite-ignore */ `${THEME}/views/settings.js`)
    const Settings = createJellySettings(sdk)
    const r = render(createElement(Settings, { onClose: vi.fn() }))
    await settle()
    const screen = r.container.querySelector('.gcs-set.jelly-settings') as HTMLElement
    expect(screen.dataset.pager).toBe('1')
    expect(r.container.querySelectorAll('.gcs-set-row')).toHaveLength(10)
    await press('gp:r1')
    expect((r.container.querySelector('.gcs-set-page') as HTMLElement).dataset.cat).toBe('bluetooth')
  })
})
