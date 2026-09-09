/**
 * The bezel and the suspended game.
 *
 * `overlay:stop` does two things in main.js: it tears the bezel down, and it
 * brings `mainWindow` back — the overlay's `window:ready` hides it. So an event
 * that takes a game off the screen without sending it leaves the player in
 * front of a frozen bezel with the interface invisible behind it, holding a
 * controller that works and has nothing to point at.
 */
import { render, act, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useEmulatorOverlay } from './useEmulatorOverlay'
import { useStore, type BackgroundSession } from '../store'

const HELD: BackgroundSession = {
  gameKey: 'Zelda.iso', systemId: 'dolphin', session: 1, kind: 'game' }

const Host = () => { useEmulatorOverlay(); return null }

let start: ReturnType<typeof vi.fn>
let stop: ReturnType<typeof vi.fn>
let screenClaim: ReturnType<typeof vi.fn>

function mount() {
  start = vi.fn(); stop = vi.fn(); screenClaim = vi.fn()
  ;(window as unknown as { gamecore: unknown }).gamecore = {
    overlayStart: start, overlayStop: stop, onOverlayHide: vi.fn(),
    sessionScreen: screenClaim,
  }
  render(<Host />)
}

const setState = (s: Parameters<typeof useStore.setState>[0]) =>
  act(() => { useStore.setState(s) })

afterEach(() => {
  cleanup()
  delete (window as unknown as { gamecore?: unknown }).gamecore
  useStore.setState({ sessionGameKey: null, sessionSystemId: null,
                      backgroundSessions: [] })
  vi.restoreAllMocks()
})

describe('the bezel follows the session on the screen', () => {
  it('appears with the game, named by its ROM', () => {
    mount()
    setState({ sessionGameKey: 'Zelda.iso', sessionSystemId: 'dolphin' })
    expect(start).toHaveBeenCalledWith('dolphin', 'Zelda.iso')
  })

  it('is taken down when the game is suspended', () => {
    mount()
    setState({ sessionGameKey: 'Zelda.iso', sessionSystemId: 'dolphin' })
    setState({ sessionGameKey: null, sessionSystemId: null,
               backgroundSessions: [HELD] })
    expect(stop).toHaveBeenCalledWith('dolphin')
  })

  it('comes back when the game is resumed', () => {
    mount()
    setState({ sessionGameKey: null, sessionSystemId: null,
               backgroundSessions: [HELD] })
    start.mockClear()
    setState({ sessionGameKey: 'Zelda.iso', sessionSystemId: 'dolphin',
               backgroundSessions: [] })
    expect(start).toHaveBeenCalledWith('dolphin', 'Zelda.iso')
  })

  it('swaps cleanly, stopping the outgoing one before starting the new', () => {
    mount()
    setState({ sessionGameKey: 'stremio', sessionSystemId: 'stremio' })
    start.mockClear()
    setState({ sessionGameKey: 'Zelda.iso', sessionSystemId: 'dolphin',
               backgroundSessions: [{ ...HELD, gameKey: 'stremio',
                                      systemId: 'stremio', kind: 'app' }] })
    expect(stop).toHaveBeenCalledWith('stremio')
    expect(start).toHaveBeenCalledWith('dolphin', 'Zelda.iso')
  })

  it('leaves the bezel alone when only the background list changes', () => {
    // Closing a suspended game must not disturb the game being played.
    mount()
    setState({ sessionGameKey: 'Zelda.iso', sessionSystemId: 'dolphin',
               backgroundSessions: [{ ...HELD, gameKey: 'other.iso', session: 2 }] })
    stop.mockClear()
    setState({ backgroundSessions: [] })
    expect(stop).not.toHaveBeenCalled()
  })
})

describe('who owns the screen', () => {
  it('tells the shell to get out of the way when a game is on screen', () => {
    mount()
    setState({ sessionGameKey: 'Zelda.iso', sessionSystemId: 'dolphin' })
    expect(screenClaim).toHaveBeenCalledWith(true)
  })

  it('gives the screen back when the game is suspended', () => {
    mount()
    setState({ sessionGameKey: 'Zelda.iso', sessionSystemId: 'dolphin' })
    screenClaim.mockClear()
    setState({ sessionGameKey: null, sessionSystemId: null,
               backgroundSessions: [HELD] })
    expect(screenClaim).toHaveBeenCalledWith(false)
  })

  it('claims it again on resume — which is the case the bezel never covered', () => {
    // A resumed emulator maps no new window: SIGCONT wakes a process whose
    // window is already there, and already under the interface. If nothing
    // hides GameCore the game comes back invisible, which is what a system
    // with no overlay config did on every resume.
    mount()
    setState({ sessionGameKey: null, sessionSystemId: null,
               backgroundSessions: [HELD] })
    screenClaim.mockClear()
    setState({ sessionGameKey: 'Zelda.iso', sessionSystemId: 'dolphin',
               backgroundSessions: [] })
    expect(screenClaim).toHaveBeenCalledWith(true)
  })

  it('says it once per change, not once per store write', () => {
    mount()
    setState({ sessionGameKey: 'Zelda.iso', sessionSystemId: 'dolphin' })
    screenClaim.mockClear()
    setState({ backgroundSessions: [HELD] })
    setState({ modalDepth: 1 })
    expect(screenClaim).not.toHaveBeenCalled()
  })
})
