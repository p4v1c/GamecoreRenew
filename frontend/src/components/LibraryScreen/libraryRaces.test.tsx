/**
 * Three ways the library answered a question nobody had asked any more.
 *
 * The screen fires three requests per console and holds the cursor in the
 * store, and none of that is instantaneous: a console with four hundred ROMs
 * answers slower than an empty one, and a d-pad step reaches the store before
 * React has rendered anything at all. Every test below is a moment where those
 * two clocks disagreed.
 *
 *  · A reply from the console you just left overwrote the one you are on.
 *  · ✕ pressed in the same frame as a step launched the previous game, and two
 *    ✕ in that frame sent two launches.
 *  · Moving the cursor re-formatted, re-filtered and re-sorted the whole
 *    library — 2 998 calls to `formatGameName` on a thousand games, to produce
 *    the order that was already on screen.
 *
 * The reproductions come from the 2026-09-04 audit (findings 1, 6 and 7); what
 * they assert here is the corrected behaviour.
 */
import React from 'react'
import { render, act, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import LibraryScreen from './index'
import { useStore } from '../../store'
import { api } from '../../api'
import * as names from '../../lib/formatGameName'
import type { LibraryViewProps } from './types'

const game = (name: string) => ({
  filename: `${name}.rom`, display_name: name, path: `/roms/${name}.rom`, size: 1, ext: '.rom',
})

/** A promise this test resolves by hand, to hold a console's reply open. */
const deferred = <T,>() => {
  let resolve!: (v: T) => void
  const promise = new Promise<T>(r => { resolve = r })
  return { promise, resolve }
}

const flush = () => act(async () => { await new Promise(r => setTimeout(r, 0)) })

/** Nothing to look at: this file is about the host, so the view is a witness. */
const Probe = (p: LibraryViewProps) => (
  <div data-testid="probe">{p.systemId}:{p.games[p.selectedIdx]?.filename}</div>
)

function setup(games = [game('Alpha'), game('Beta')]) {
  useStore.setState({
    screen: 'library', selectedSystemId: 'gc', selectedGameIdx: 0,
    modalDepth: 0, sessionGameKey: null,
  })
  vi.spyOn(api.systems, 'get').mockImplementation(async id => ({ id, kind: 'emulator', label: id }))
  vi.spyOn(api.games, 'list').mockResolvedValue(games)
  vi.spyOn(api.playtime, 'forSystem').mockResolvedValue([])
  vi.spyOn(api.games, 'launch').mockResolvedValue({ ok: true, game_key: 'Alpha.rom' } as never)
}

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('the library and the requests it has stopped waiting for', () => {
  it('ignores a late reply from the console the player has left', async () => {
    setup()
    const old = deferred<ReturnType<typeof game>[]>()
    vi.mocked(api.games.list).mockImplementation(
      id => id === 'gc' ? old.promise : Promise.resolve([game('PS2')]),
    )
    const r = render(<LibraryScreen view={Probe} />); await flush()
    act(() => useStore.setState({ selectedSystemId: 'ps2' })); await flush()
    expect(r.getByTestId('probe').textContent).toBe('ps2:PS2.rom')
    // GameCube finally answers. Before the fix this rendered `ps2:GameCube.rom`
    // — and asked for covers, and offered ✕ on a pair that does not exist.
    await act(async () => { old.resolve([game('GameCube')]); await old.promise }); await flush()
    expect(r.getByTestId('probe').textContent).toBe('ps2:PS2.rom')
  })

  it('does not let a stale failure replace a library that loaded', async () => {
    setup()
    let rejectOld!: (e: Error) => void
    const old = new Promise<ReturnType<typeof game>[]>((_, reject) => { rejectOld = reject })
    old.catch(() => {})   // the test resolves this failure itself; nothing is unhandled
    vi.mocked(api.games.list).mockImplementation(
      id => id === 'gc' ? old : Promise.resolve([game('PS2')]),
    )
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const Witness = (p: LibraryViewProps) => <div data-testid="probe">{p.loadError ? 'error' : p.systemId}</div>
    const r = render(<LibraryScreen view={Witness} />); await flush()
    act(() => useStore.setState({ selectedSystemId: 'ps2' })); await flush()
    await act(async () => { rejectOld(new Error('timeout')); await old.catch(() => {}) })
    await flush()
    expect(r.getByTestId('probe').textContent).toBe('ps2')
  })

  it('launches the game the cursor is on, not the one the last render saw', async () => {
    setup(); render(<LibraryScreen view={Probe} />); await flush()
    act(() => {
      window.dispatchEvent(new CustomEvent('gp:dpad-down'))
      window.dispatchEvent(new CustomEvent('gp:confirm'))
    })
    await flush()
    expect(useStore.getState().selectedGameIdx).toBe(1)
    expect(api.games.launch).toHaveBeenCalledWith('gc', '/roms/Beta.rom', 'Beta.rom')
  })

  it('sends one launch for two ✕ in the same frame', async () => {
    setup(); render(<LibraryScreen view={Probe} />); await flush()
    act(() => {
      window.dispatchEvent(new CustomEvent('gp:confirm'))
      window.dispatchEvent(new CustomEvent('gp:confirm'))
    })
    await flush()
    expect(api.games.launch).toHaveBeenCalledTimes(1)
  })

  it('formats no name at all when only the cursor moves', async () => {
    setup(Array.from({ length: 1000 }, (_, i) => game(`Game ${String(i).padStart(4, '0')}`)))
    const spy = vi.spyOn(names, 'formatGameName')
    const r = render(<LibraryScreen view={Probe} />); await flush(); spy.mockClear()
    const before = r.getByTestId('probe').textContent
    act(() => window.dispatchEvent(new CustomEvent('gp:dpad-down')))
    expect(spy.mock.calls.length).toBe(0)
    expect(r.getByTestId('probe').textContent).not.toBe(before)
  })
})
