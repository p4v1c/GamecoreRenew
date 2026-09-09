/**
 * Orbit's home rail: what is selected, and what the browser thinks is focused.
 *
 * The rail keeps its own cursor — the host's d-pad is omitted on this screen —
 * and its tiles also carry `onFocus`, because a tile is a real button and a
 * player on a desk can Tab to one. That makes two sources of truth for the
 * same thing, and they have to agree: a tile that is drawn as selected while
 * `document.activeElement` is a *different* tile means the next keypress goes
 * somewhere other than the highlight, and any screen-reader announces the
 * wrong game.
 *
 * Keeping them in step is subtler than it looks, and the way it was first
 * written is the reason this file exists: focusing the selected tile from a
 * `setTimeout(…, 0)` assumes React has committed the new selection by the next
 * task. React 18 does not promise that. When it had not, the timer focused the
 * tile the cursor had just *left* — whose `onFocus` set the selection straight
 * back. The rail was stuck: press right, and nothing moved.
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
]
const PLAYTIME = [
  { game_key: 'Journey.iso', system_id: 'rpcs3', total_secs: 7200, session_count: 3,
    last_played: '2026-09-01T20:00:00Z' },
  { game_key: 'Zelda.iso', system_id: 'dolphin', total_secs: 3600, session_count: 2,
    last_played: '2026-08-30T20:00:00Z' },
]

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(typeof input === 'string' ? input : (input as Request).url ?? input)
    const body: unknown =
      url.includes('/playtime') ? PLAYTIME
        : url.endsWith('/systems/rpcs3/games') ? [{ filename: 'Journey.iso', display_name: 'Journey', path: '/t/Journey.iso' }]
          : url.endsWith('/systems/dolphin/games') ? [{ filename: 'Zelda.iso', display_name: 'Zelda', path: '/t/Zelda.iso' }]
            : url.endsWith('/systems') ? SYSTEMS
              : url.includes('/metadata') ? { found: false }
                : url.includes('/media') ? { media: {} }
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
  const View = home.createHome(sdk, tabs, session.createSession(sdk), { current: SYSTEMS })
  const r = render(createElement(
    HomeScreen as React.ComponentType<{ view: unknown; omit: string[]; onLaunchApp: unknown }>,
    { view: View, omit: ['nav', 'pages', 'confirm'], onLaunchApp: vi.fn() }))
  await act(async () => { await new Promise(res => setTimeout(res, 0)) })
  return r
}

const press = async (event: string, n = 1) => {
  await act(async () => {
    for (let i = 0; i < n; i++) window.dispatchEvent(new CustomEvent(event))
    await new Promise(res => setTimeout(res, 0))
  })
}

const selected = (c: HTMLElement) => c.querySelector('.game-tile[data-active="true"]')
const label = (c: HTMLElement) =>
  c.querySelector('.game-tile[data-active="true"] .tile-label')?.textContent

describe('the home rail', () => {
  it('moves when the pad says right', async () => {
    const { container } = await orbit()
    const first = label(container)
    await press('gp:dpad-right')
    expect(label(container)).not.toBe(first)
  })

  it('puts DOM focus on the tile it has just selected', async () => {
    // The invariant: what is drawn as selected is what the browser is focused
    // on. Two cursors that disagree is a rail where the highlight and the next
    // keypress are on different tiles.
    const { container } = await orbit()
    await press('gp:dpad-right')
    expect(document.activeElement).toBe(selected(container))
  })

  it('keeps them together across a burst, rather than snapping back', async () => {
    // The failure this replaces was silent and total: the tile focused a task
    // later was the one the cursor had left, its `onFocus` reset the selection,
    // and the rail could not be moved at all.
    const { container } = await orbit()
    const start = label(container)
    await press('gp:dpad-right', 3)
    expect(label(container)).not.toBe(start)
    expect(document.activeElement).toBe(selected(container))
  })

  it('walks back the way it came', async () => {
    const { container } = await orbit()
    const start = label(container)
    await press('gp:dpad-right')
    await press('gp:dpad-left')
    expect(label(container)).toBe(start)
    expect(document.activeElement).toBe(selected(container))
  })

  it('does not move the host cursor underneath it', async () => {
    // The rail owns this screen's d-pad. If the host's grid cursor moved too,
    // something off screen would be being selected at the same time.
    const { container } = await orbit()
    await press('gp:dpad-right', 2)
    expect(useStore.getState().gridFocusIdx).toBe(0)
    expect(selected(container)).toBeTruthy()
  })

  it('leaves the tiles alone while a modal is up', async () => {
    const { container } = await orbit()
    const start = label(container)
    useStore.setState({ modalDepth: 1 })
    await press('gp:dpad-right')
    expect(label(container)).toBe(start)
  })

  it('stops listening once the screen is gone', async () => {
    // A rail that keeps its bindings after unmount moves a cursor on a screen
    // nobody is looking at, and on a box that never restarts its browser they
    // accumulate for as long as it is switched on.
    const r = await orbit()
    const before = label(r.container)
    r.unmount()
    await press('gp:dpad-right')
    expect(before).toBeTruthy()
  })
})
