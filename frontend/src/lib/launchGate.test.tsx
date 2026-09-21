import { act, cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '../api'
import { useStore } from '../store'
import { gateGameLaunch } from './launchGate'
import LaunchConflictModal from '../components/modals/LaunchConflictModal'

const held = {
  gameKey: 'Zelda_(USA).iso', systemId: 'dolphin', session: 7,
  kind: 'game' as const,
}

beforeEach(() => {
  useStore.setState({
    sessionGameKey: null, sessionSystemId: null,
    backgroundSessions: [held], launchConflict: null,
  })
})

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('resumes the same game without sending a second launch', async () => {
  const foreground = vi.spyOn(api.games, 'foreground').mockResolvedValue({
    game_key: held.gameKey, system_id: held.systemId, session: held.session,
    state: 'foreground', kind: 'game',
  })

  await expect(Promise.resolve(gateGameLaunch(held.systemId, held.gameKey))).resolves.toBe('resumed')
  expect(foreground).toHaveBeenCalledWith(held.session)
  expect(useStore.getState().sessionGameKey).toBe(held.gameKey)
  expect(useStore.getState().backgroundSessions).toEqual([])
})

it('blocks a different game and raises the host-owned themed dialog', async () => {
  await expect(Promise.resolve(gateGameLaunch('pcsx2', 'Shadow.iso'))).resolves.toBe('blocked')
  expect(useStore.getState().launchConflict).toEqual(held)

  const r = render(<LaunchConflictModal />)
  expect(r.getByRole('alertdialog').textContent).toContain('Another game is still running')
  expect(r.getByRole('alertdialog').textContent).toContain('Close Zelda')
  fireEvent.click(r.getByRole('button', { name: 'OK' }))
  expect(useStore.getState().launchConflict).toBeNull()
})

it('does not apply the game-only gate to a background application', async () => {
  act(() => useStore.setState({
    backgroundSessions: [{ gameKey: 'youtube', systemId: 'youtube', session: 8, kind: 'app' }],
  }))
  await expect(Promise.resolve(gateGameLaunch('dolphin', 'Zelda.iso'))).resolves.toBe('launch')
})
