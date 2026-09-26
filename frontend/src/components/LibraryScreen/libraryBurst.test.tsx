/**
 * A burst of d-pad presses moves the cursor by that many rows.
 *
 * Handlers used to read `selectedGameIdx` from their effect closure, which is
 * refreshed only after React commits; presses inside that window recomputed
 * the same index and were lost (the "stuttering shelf"). Dispatching without
 * yielding reproduces it. Fix: step from `getState()`, never from a snapshot.
 */
import { render, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useStore } from '../../store'
import LibraryScreen from './index'
import type { LibraryViewProps } from './types'

const GAMES = Array.from({ length: 60 }, (_, i) => ({
  filename: `game-${String(i).padStart(3, '0')}.rom`,
  display_name: `Game ${String(i).padStart(3, '0')}`,
  path: `/roms/game-${i}.rom`,
  ext: '.rom',
}))

/** Nothing to look at: this file is about the host, so the view is a witness. */
const Probe = (p: LibraryViewProps) =>
  <div data-testid="probe" data-idx={String(p.selectedIdx)} data-name={p.games[p.selectedIdx]?.display_name ?? ''} />

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(typeof input === 'string' ? input : (input as Request).url ?? input)
    const body: unknown = url.includes('/games') ? GAMES
      : url.includes('/systems/') ? { id: 'gc', label: 'GameCube', color: '#6a5acd' }
        : []
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
  useStore.setState({
    screen: 'library', selectedSystemId: 'gc', selectedGameIdx: 0,
    modalDepth: 0, sessionGameKey: null,
  })
})

afterEach(async () => {
  const { cleanup } = await import('@testing-library/react')
  cleanup()
  vi.unstubAllGlobals()
})

async function mount() {
  const r = render(<LibraryScreen view={Probe} />)
  await act(async () => { await new Promise(res => setTimeout(res, 0)) })
  return r
}

/** All of them, in one go, with no chance for React to render in between —
 *  which is the whole point. */
const burst = async (event: string, n: number) => {
  await act(async () => {
    for (let i = 0; i < n; i++) window.dispatchEvent(new CustomEvent(event))
  })
}

describe('the library cursor under a burst of presses', () => {
  it('moves one row per press, however fast they arrive', async () => {
    await mount()
    await burst('gp:dpad-down', 5)
    expect(useStore.getState().selectedGameIdx).toBe(5)
  })

  it('comes back up the same number of rows', async () => {
    await mount()
    await burst('gp:dpad-down', 8)
    await burst('gp:dpad-up', 3)
    expect(useStore.getState().selectedGameIdx).toBe(5)
  })

  it('still stops at the ends of the list', async () => {
    await mount()
    await burst('gp:dpad-up', 4)
    expect(useStore.getState().selectedGameIdx).toBe(0)
    await burst('gp:dpad-down', GAMES.length + 20)
    expect(useStore.getState().selectedGameIdx).toBe(GAMES.length - 1)
  })

  it('leaves the view showing the row the cursor is on', async () => {
    // The measurable half of "the focus and what is drawn agree". A cursor
    // that ran ahead of the markup would be a different bug with the same
    // symptom, so it is asserted rather than assumed.
    const { getByTestId } = await mount()
    await burst('gp:dpad-down', 7)
    await act(async () => { await new Promise(res => setTimeout(res, 0)) })
    expect(getByTestId('probe').getAttribute('data-idx')).toBe('7')
    expect(getByTestId('probe').getAttribute('data-name')).toBe('Game 007')
  })

  it('does not move while a modal owns the pad', async () => {
    await mount()
    act(() => { useStore.setState({ modalDepth: 1 }) })
    await burst('gp:dpad-down', 5)
    expect(useStore.getState().selectedGameIdx).toBe(0)
  })
})
