/**
 * The launch cover relay: up on `game:loading`, down on the signal, a failure
 * or the end of THAT launch, and deaf to events about another game.
 */
import { render, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useLaunchCover } from './useLaunchCover'

const handlers = new Map<string, (d: Record<string, unknown>) => void>()
vi.mock('./useWebSocket', () => ({
  onWsEvent: (event: string, handler: (d: Record<string, unknown>) => void) => {
    handlers.set(event, handler)
    return () => handlers.delete(event)
  },
}))

const Host = () => { useLaunchCover(); return null }
const emit = (event: string, data: Record<string, unknown>) => handlers.get(event)?.(data)
const UNCHARTED = { game_key: 'Uncharted 2.sh', system_id: 'rpcs3' }
let show: ReturnType<typeof vi.fn>
let hide: ReturnType<typeof vi.fn>

beforeEach(() => {
  handlers.clear()
  show = vi.fn(); hide = vi.fn()
  ;(window as unknown as { gamecore: unknown }).gamecore = { coverShow: show, coverHide: hide }
  render(<Host />)
})
afterEach(() => {
  cleanup()
  delete (window as unknown as { gamecore?: unknown }).gamecore
})

it('raises the cover for the launch and drops it on its signal', () => {
  emit('game:loading', { ...UNCHARTED, timeout_s: 240 })
  expect(show).toHaveBeenCalledWith({ ...UNCHARTED, timeout_s: 240 })
  emit('game:ready', { ...UNCHARTED, reason: 'signal' })
  expect(hide).toHaveBeenCalledTimes(1)
})

it.each(['game:failed', 'game:finished'])('drops it when the launch ends with %s', (event) => {
  emit('game:loading', UNCHARTED)
  emit(event, UNCHARTED)
  expect(hide).toHaveBeenCalledTimes(1)
})

it('ignores an event about another game', () => {
  emit('game:loading', UNCHARTED)
  emit('game:finished', { game_key: 'Zelda.iso', system_id: 'gamecube' })
  expect(hide).not.toHaveBeenCalled()
})

it('does nothing on a shell without the cover', () => {
  ;(window as unknown as { gamecore: unknown }).gamecore = {}
  emit('game:loading', UNCHARTED)
  emit('game:ready', UNCHARTED)
  expect(show).not.toHaveBeenCalled()
})
