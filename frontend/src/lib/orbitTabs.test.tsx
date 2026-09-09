/**
 * Orbit's four tabs, against the real host and the real SDK.
 *
 * The theme was rebuilt from the interactive mockup, whose whole shape is the
 * navigation: Games, Consoles, Library, Applications. A syntax check says
 * nothing about whether those render, and the previous version of this theme
 * shipped a home that silently disagreed with the host's cursor. So the views
 * are mounted through the assembly `index.js` builds — same host screens, same
 * `homeOmit` — and asserted on what can be asserted from jsdom: which tab is
 * drawn, what is on it, and where the pad moves.
 *
 * How it LOOKS on a television is the owner's to judge and is claimed nowhere
 * below.
 */
import { render, act, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React, { createElement } from 'react'
import { buildSdk } from './themeSdk'
import { useStore } from '../store'
import HomeScreen from '../components/HomeScreen'

const THEME = '../../../config/themes/orbit'

const SYSTEMS = [
  { id: 'rpcs3', label: 'RPCS3', kind: 'emulator' as const },
  { id: 'dolphin', label: 'Dolphin', kind: 'emulator' as const },
  { id: 'stremio', label: 'Stremio', kind: 'app' as const },
  { id: 'youtube', label: 'YouTube', kind: 'app' as const },
]
const PLAYTIME = [
  { game_key: 'Journey.iso', system_id: 'rpcs3', total_secs: 7200, session_count: 3,
    last_played: '2026-09-01T20:00:00Z' },
  { game_key: 'Zelda_(USA).iso', system_id: 'dolphin', total_secs: 3600, session_count: 2,
    last_played: '2026-08-30T20:00:00Z' },
]

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(typeof input === 'string' ? input : (input as Request).url ?? input)
    const body: unknown =
      url.includes('/playtime') ? PLAYTIME
        : url.includes('/systems') ? SYSTEMS
          : url.includes('/metadata') ? { found: false }
            : []
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
  useStore.setState({
    screen: 'home', selectedSystemId: null, gridFocusIdx: 0, gridPage: 0,
    modalDepth: 0, sessionGameKey: null, sessionSystemId: null,
    backgroundSessions: [], powerPending: null, standby: 'off',
  })
})

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

async function orbit() {
  const sdk = buildSdk('orbit', { selectTheme: vi.fn(async () => {}) })
  const load = (p: string) => import(/* @vite-ignore */ p)
  const [home, tabsMod, session] = await Promise.all([
    load(`${THEME}/views/home.js`),
    load(`${THEME}/lib/tabs.js`),
    load(`${THEME}/lib/session.js`),
  ])
  const tabs = tabsMod.createTabs(sdk)
  const systemsRef = { current: SYSTEMS }
  const View = home.createHome(sdk, tabs, session.createSession(sdk), systemsRef)
  // The same omissions index.js declares: without them the host's cursor walks
  // the system grid underneath a rail of games.
  const r = render(createElement(
    HomeScreen as React.ComponentType<{ view: unknown; omit: string[]; onLaunchApp: unknown }>,
    { view: View, omit: ['nav', 'pages', 'confirm'], onLaunchApp: vi.fn() }))
  await act(async () => { await new Promise(res => setTimeout(res, 0)) })
  return { ...r, tabs, sdk }
}

const press = async (event: string, n = 1) => {
  await act(async () => {
    for (let i = 0; i < n; i++) window.dispatchEvent(new CustomEvent(event))
    await new Promise(res => setTimeout(res, 0))
  })
}

describe('the Games tab', () => {
  it('is what the home screen opens on', async () => {
    const { container } = await orbit()
    expect(container.querySelector('#home-view')).toBeTruthy()
    expect(container.querySelector('.game-rail')).toBeTruthy()
  })

  it('builds its rail from what was actually played, not from a bundled list', async () => {
    // The mockup shipped twelve invented titles. A theme that kept them would
    // be showing the player a library they do not own.
    const { container } = await orbit()
    const labels = [...container.querySelectorAll('.tile-label')].map(el => el.textContent)
    expect(labels).toContain('Journey')
    expect(labels).toContain('Zelda')
    expect(labels).toContain('Collection')
  })

  it('puts the applications on the same rail', async () => {
    const { container } = await orbit()
    expect(container.querySelectorAll('.home-app-tile').length).toBe(2)
  })

  it('moves its own cursor, because the host is not moving one underneath', async () => {
    const { container } = await orbit()
    const first = container.querySelector('.game-tile[data-active="true"] .tile-label')?.textContent
    await press('gp:dpad-right')
    const second = container.querySelector('.game-tile[data-active="true"] .tile-label')?.textContent
    expect(second).not.toBe(first)
    // And the host's own cursor stayed where it was: nothing is being selected
    // off screen.
    expect(useStore.getState().gridFocusIdx).toBe(0)
  })
})

describe('the tabs', () => {
  it('walk with L1 and R1', async () => {
    const { container } = await orbit()
    await press('gp:r1')
    expect(container.querySelector('#systems-view')).toBeTruthy()
    await press('gp:l1')
    expect(container.querySelector('#home-view')).toBeTruthy()
  })

  it('draw the consoles without the applications mixed into them', async () => {
    const { container } = await orbit()
    await press('gp:r1')
    const tiles = [...container.querySelectorAll('.machine-tile')]
    expect(tiles.length).toBe(2)
    expect(container.querySelector('.console-showcase h2')?.textContent)
      .toBe('PlayStation 3')
  })

  it('draw the applications without the consoles mixed into them', async () => {
    const { container, tabs } = await orbit()
    await act(async () => { tabs.go('applications', SYSTEMS) })
    expect(container.querySelectorAll('.application-tile').length).toBe(2)
    expect(container.querySelector('#applications-view')).toBeTruthy()
  })

  it('send Library to the host screen rather than drawing a second one', async () => {
    // The library is the one tab with behaviour behind it — sort, the search
    // keyboard, per-game options, the launch. Orbit asks the host for it.
    const { tabs } = await orbit()
    await act(async () => { tabs.go('library', SYSTEMS) })
    expect(useStore.getState().screen).toBe('library')
    expect(useStore.getState().selectedSystemId).toBe('rpcs3')
  })
})

describe('the Consoles tab', () => {
  it('opens the console it is showing', async () => {
    const { container } = await orbit()
    await press('gp:r1')
    await press('gp:dpad-right')
    expect(container.querySelector('.console-showcase h2')?.textContent)
      .toBe('GameCube & Wii')
    await press('gp:confirm')
    expect(useStore.getState().screen).toBe('library')
    expect(useStore.getState().selectedSystemId).toBe('dolphin')
  })
})
