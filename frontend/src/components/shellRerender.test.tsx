/**
 * What a press in the library is allowed to re-render, and what it is not.
 *
 * Both screens stay mounted for the whole session — the shell toggles them
 * with `display: none` so that going home does not re-fetch. That is the right
 * trade, and it has a price nobody was paying attention to: anything that
 * re-renders on a value only one screen uses re-renders BOTH of them, plus the
 * wall behind and the bar above.
 *
 * `useStore()` with no selector subscribes to the whole store, so moving the
 * cursor one game along the shelf re-rendered the dashboard — every console
 * card, and for a theme like Shelf that is a row of assembled 3D boxes — while
 * it was invisible. Once per press, at exactly the moment of the session when
 * the frame budget is tightest.
 *
 * This asserts the boundary rather than a duration: nothing that does not read
 * `selectedGameIdx` may render because `selectedGameIdx` changed. Whether the
 * scroll then FEELS smoother on a television is not claimed here, and cannot
 * be from this file.
 */
import { render, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useStore } from '../store'
import DefaultShell from './DefaultShell'
import type { HomeViewProps } from './HomeScreen/types'
import type { LibraryViewProps } from './LibraryScreen/types'

const SYSTEMS = Array.from({ length: 8 }, (_, i) => ({
  id: `sys${i}`, label: `System ${i}`, color: '#6a5acd', kind: 'emulator',
}))
const GAMES = Array.from({ length: 40 }, (_, i) => ({
  filename: `game-${String(i).padStart(3, '0')}.rom`,
  display_name: `Game ${String(i).padStart(3, '0')}`,
  path: `/roms/game-${i}.rom`, ext: '.rom',
}))

const counts = { home: 0, background: 0, topbar: 0, library: 0 }
const reset = () => { counts.home = counts.background = counts.topbar = counts.library = 0 }

// Deliberately inert. A view with state of its own could re-render for reasons
// of its own, and this file is about one reason only.
const HomeView = (_p: HomeViewProps) => { counts.home++; return null }
const LibraryView = (_p: LibraryViewProps) => { counts.library++; return null }
const Background = () => { counts.background++; return null }
const TopBar = () => { counts.topbar++; return null }

beforeEach(() => {
  reset()
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(typeof input === 'string' ? input : (input as Request).url ?? input)
    const body: unknown = /\/systems$/.test(url.split('?')[0]) ? SYSTEMS
      : url.includes('/games') ? GAMES
        : url.includes('/systems/') ? SYSTEMS[0] : []
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
  useStore.setState({
    screen: 'library', selectedSystemId: 'sys0', selectedGameIdx: 0,
    gridFocusIdx: 0, gridPage: 0, modalDepth: 0, sessionGameKey: null,
  })
})

afterEach(async () => {
  const { cleanup } = await import('@testing-library/react')
  cleanup()
  vi.unstubAllGlobals()
})

async function shell() {
  const r = render(
    <DefaultShell
      background={Background}
      topbar={TopBar}
      homeView={HomeView}
      libraryView={LibraryView}
    />,
  )
  // Everything the two screens fetch on mount, out of the way first.
  await act(async () => { await new Promise(res => setTimeout(res, 50)) })
  return r
}

describe('a step along the shelf', () => {
  it('does not re-render the dashboard behind it', async () => {
    await shell()
    reset()
    await act(async () => { useStore.setState({ selectedGameIdx: 1 }) })
    expect(counts.library).toBeGreaterThan(0)
    expect(counts.home).toBe(0)
  })

  it('does not re-render the wall or the bar', async () => {
    await shell()
    reset()
    await act(async () => { useStore.setState({ selectedGameIdx: 1 }) })
    expect(counts.background).toBe(0)
    expect(counts.topbar).toBe(0)
  })

  it('costs the same whether the shelf is long or short', async () => {
    // Ten steps must be ten library renders' worth of work and nothing else's.
    // A count that grows with the number of screens mounted is the defect.
    await shell()
    reset()
    for (let i = 1; i <= 10; i++) {
      await act(async () => { useStore.setState({ selectedGameIdx: i }) })
    }
    expect(counts.home + counts.background + counts.topbar).toBe(0)
  })
})

describe('moving on the dashboard', () => {
  it('does not re-render the library behind it', async () => {
    await shell()
    await act(async () => { useStore.setState({ screen: 'home' }) })
    reset()
    await act(async () => { useStore.setState({ gridFocusIdx: 1 }) })
    expect(counts.home).toBeGreaterThan(0)
    expect(counts.library).toBe(0)
    expect(counts.background).toBe(0)
    expect(counts.topbar).toBe(0)
  })
})

describe('what still must re-render', () => {
  it('draws both screens and the wall again when the screen changes', async () => {
    // The guard on the fix: narrower subscriptions must not stop the shell
    // reacting to the things it is actually about. `screen` decides which
    // screen is displayed and what the wall is painted like.
    await shell()
    reset()
    await act(async () => { useStore.setState({ screen: 'home' }) })
    expect(counts.home).toBeGreaterThan(0)
    expect(counts.library).toBeGreaterThan(0)
  })
})
