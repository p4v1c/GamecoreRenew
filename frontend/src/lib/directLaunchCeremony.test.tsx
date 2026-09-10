import { act, cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createElement } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import { buildSdk } from './themeSdk'

const game = { systemId: 'ps3', path: '/test/Journey.iso', gameKey: 'Journey.iso' }

beforeEach(() => {
  vi.useFakeTimers()
  useStore.setState({ screen: 'home', sessionGameKey: null, sessionSystemId: null, transition: null })
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers() })

it('shows Orbit travel in place before the emulator can take the screen', async () => {
  const path = '../../../config/themes/orbit/views/ceremony.js'
  const { createCeremony } = await import(/* @vite-ignore */ path)
  const sdk = buildSdk('orbit', { selectTheme: vi.fn(), launchMs: 400 })
  const launch = vi.spyOn(api.games, 'launch').mockResolvedValue({ ok: true } as never)
  const view = render(createElement(createCeremony(sdk)))
  let request!: Promise<void>
  act(() => { request = sdk.defaults.launchGame(game) })
  expect(view.container.querySelector('.orbit-ceremony[data-dir="away"]')).toBeTruthy()
  await act(async () => { await vi.advanceTimersByTimeAsync(399) })
  expect(launch).not.toHaveBeenCalled()
  expect(useStore.getState().screen).toBe('home')
  // A second click during the animation cannot enqueue a second launch.
  await sdk.defaults.launchGame(game)
  await act(async () => { await vi.advanceTimersByTimeAsync(1); await request })
  expect(launch).toHaveBeenCalledTimes(1)
  expect(launch).toHaveBeenCalledWith('ps3', game.path, game.gameKey)
  expect(useStore.getState().transition).toBeNull()
  expect(useStore.getState().screen).toBe('home')
})

it('does not launch if the handover was cleared before it finished', async () => {
  const sdk = buildSdk('orbit', { selectTheme: vi.fn(), launchMs: 400 })
  const launch = vi.spyOn(api.games, 'launch')
  const request = sdk.defaults.launchGame(game)
  useStore.getState().setTransition(null)
  await vi.advanceTimersByTimeAsync(400)
  await request
  expect(launch).not.toHaveBeenCalled()
})
