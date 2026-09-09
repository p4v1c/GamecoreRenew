import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LibraryScreen from './index'
import type { LibraryViewProps } from './types'
import { ThemeProvider } from '../ThemeSurface'
import { useStore } from '../../store'
import { api } from '../../api'

const GAME = {
  filename: 'Journey.iso', display_name: 'Journey', path: '/roms/Journey.iso', ext: '.iso', size: 1,
}

const View = (props: LibraryViewProps) =>
  <button onClick={props.onLaunch}>Launch</button>

const theme = {
  manifest: { launch: { ms: 100 } }, surfaces: {}, themeId: 'test', loading: false,
  safeMode: null, resetKey: 'test', reload: () => {}, select: async () => {},
  noteShellCrash: () => {},
} as any

async function mount() {
  render(<ThemeProvider value={theme}><LibraryScreen view={View} /></ThemeProvider>)
  await act(async () => { await Promise.resolve(); await Promise.resolve() })
}

beforeEach(() => {
  vi.useFakeTimers()
  useStore.setState({
    screen: 'library', selectedSystemId: 'ps3', selectedGameIdx: 0,
    modalDepth: 0, sessionGameKey: null, sessionSystemId: null, transition: null,
  })
  vi.spyOn(api.systems, 'get').mockResolvedValue({ id: 'ps3', label: 'PS3', kind: 'emulator' } as never)
  vi.spyOn(api.games, 'list').mockResolvedValue([GAME])
  vi.spyOn(api.playtime, 'forSystem').mockResolvedValue([])
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.useRealTimers()
  useStore.setState({ transition: null })
})

describe('the launch handover', () => {
  it('finishes the theme hold before sending the launch', async () => {
    const launch = vi.spyOn(api.games, 'launch').mockResolvedValue({ ok: true } as never)
    await mount()

    fireEvent.click(screen.getByText('Launch'))
    expect(useStore.getState().transition).toBe('launch')
    expect(launch).not.toHaveBeenCalled()

    await act(async () => { await vi.advanceTimersByTimeAsync(99) })
    expect(launch).not.toHaveBeenCalled()
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    expect(launch).toHaveBeenCalledWith('ps3', '/roms/Journey.iso', 'Journey.iso')
    expect(useStore.getState().transition).toBeNull()
  })

  it('cancels the hold and clears the ceremony when the player goes back', async () => {
    const launch = vi.spyOn(api.games, 'launch').mockResolvedValue({ ok: true } as never)
    await mount()
    fireEvent.click(screen.getByText('Launch'))

    act(() => { window.dispatchEvent(new CustomEvent('gp:back')) })
    expect(useStore.getState().transition).toBeNull()
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    expect(launch).not.toHaveBeenCalled()
  })

  it('clears the ceremony when the launch request fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(api.games, 'launch').mockRejectedValue(new Error('launch failed'))
    await mount()
    fireEvent.click(screen.getByText('Launch'))
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    expect(useStore.getState().transition).toBeNull()
    expect(useStore.getState().sessionGameKey).toBeNull()
  })
})
