/**
 * ≡ opens the per-game options on a library game and Settings everywhere else.
 *
 * The overlay picker used to hang off R2, which Shelf binds to restack its
 * shelf, so Shelf dropped it and the picker had no route there at all. One
 * shell handler now decides what ≡ opens, so a press cannot open both and no
 * theme option can remove the route.
 */
import { render, act, screen, cleanup, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useStore } from '../store'
import DefaultShell from './DefaultShell'
import type { LibraryViewProps } from './LibraryScreen/types'

const GAMES = [{ filename: 'crash.cue', display_name: 'Crash', path: '/roms/crash.cue', ext: '.cue' }]

const Inert = () => null
const LibraryView = (_p: LibraryViewProps) => null
const Settings = () => <div>Settings screen</div>

let games: unknown[] = GAMES

beforeEach(() => {
  games = GAMES
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body: unknown = url.includes('/games') ? games
      : url.includes('/systems/') ? { id: 'psx', label: 'PlayStation' } : []
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
  useStore.setState({ screen: 'library', selectedSystemId: 'psx', selectedGameIdx: 0,
                      modalDepth: 0, sessionGameKey: null, gameOptions: null })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const press = (name: string) => act(() => { window.dispatchEvent(new CustomEvent(name)) })

async function shell(parts: { libraryOmit?: string[] } = {}) {
  render(<DefaultShell background={Inert} topbar={Inert} homeView={Inert as never}
                       libraryView={LibraryView} settings={Settings} {...parts} />)
  // The library has loaded and its cursor has settled on a game (150 ms).
  if (games.length) await waitFor(() => expect(useStore.getState().gameOptions).not.toBeNull())
  else await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/games')))
}

describe('≡ in the library', () => {
  it('opens the game’s options, not Settings', async () => {
    await shell()
    press('gp:menu')
    expect(screen.getByText('Game options')).toBeTruthy()
    expect(screen.queryByText('Settings screen')).toBeNull()
  })

  it('closes them again', async () => {
    await shell()
    press('gp:menu')
    expect(screen.getByText('Game options')).toBeTruthy()
    press('gp:menu')
    await waitFor(() => expect(screen.queryByText('Game options')).toBeNull())
    expect(screen.queryByText('Settings screen')).toBeNull()
  })

  it('still opens them when a theme lists the old “options” omission', async () => {
    await shell({ libraryOmit: ['options'] })
    press('gp:menu')
    expect(screen.getByText('Game options')).toBeTruthy()
  })

  it('opens Settings when there is no game to set up', async () => {
    games = []
    await shell()
    press('gp:menu')
    expect(screen.getByText('Settings screen')).toBeTruthy()
  })

  it('no longer answers R2', async () => {
    await shell()
    press('gp:r2')
    expect(screen.queryByText('Game options')).toBeNull()
  })
})

describe('≡ on the dashboard', () => {
  it('opens Settings, even with a game settled in the hidden library', async () => {
    await shell()
    act(() => { useStore.setState({ screen: 'home' }) })
    press('gp:menu')
    expect(screen.getByText('Settings screen')).toBeTruthy()
    expect(screen.queryByText('Game options')).toBeNull()
  })
})
