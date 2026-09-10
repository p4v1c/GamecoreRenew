/**
 * The frontend half of suspending a game, and the lock it turned on.
 *
 * `useGamepad` blocks every press while `sessionGameKey` is set, so that an
 * emulator's inputs cannot drive the interface behind it. That rule is right
 * and stays — but a suspended game is not on the screen, and leaving the key
 * set for one would have frozen the interface exactly when the player needs
 * it: their session visible on a bar they cannot select, on a box where no
 * button does anything. The fix is that `sessionGameKey` keeps meaning "a game
 * owns the screen", so a suspended session writes null and every reader of it
 * — the pad guard, the shell's decor, the library's bindings — becomes right
 * without being touched.
 *
 * The reconnection half matters just as much. A socket lost while a game was
 * suspended and regained after it was closed must not leave a session bar
 * offering to resume a game that no longer exists.
 */
import { render, act, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useWebSocket } from './useWebSocket'
import { isPlaying } from './useGamepad'
import { useStore } from '../store'
import { api } from '../api'

class FakeSocket {
  static instances: FakeSocket[] = []
  readyState = 1
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  constructor() { FakeSocket.instances.push(this) }
  close() { this.readyState = 3; this.onclose?.() }
}

const send = (socket: FakeSocket, event: string, data: Record<string, unknown> = {}) =>
  act(() => { socket.onmessage?.({ data: JSON.stringify({ event, data }) }) })

const Host = () => { useWebSocket(); return null }

/** The shape `/api/games/session` and both lifecycle events carry. */
const state = (fg: Record<string, unknown> | null,
               bg: Record<string, unknown>[] = []) => ({
  ...(fg ?? {}),
  ...(bg.length ? { background: bg } : {}),
})

const GAME = { game_key: 'zelda.iso', system_id: 'dolphin', session: 1,
               state: 'foreground', kind: 'game' }
const SUSPENDED = { game_key: 'zelda.iso', system_id: 'dolphin', session: 1,
                    state: 'background', kind: 'game' }
const APP = { game_key: 'stremio', system_id: 'stremio', session: 2,
              state: 'foreground', kind: 'app' }

afterEach(() => {
  cleanup()
  FakeSocket.instances.forEach(s => { s.onclose = null; s.readyState = 3 })
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers()
  FakeSocket.instances = []
  useStore.setState({ sessionGameKey: null, sessionSystemId: null,
                      backgroundSessions: [], transition: null })
})

function mountView() {
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.spyOn(api.standby, 'get').mockResolvedValue({ state: 'active' } as never)
  vi.spyOn(api.games, 'session').mockResolvedValue({} as never)
  const view = render(<Host />)
  return { socket: FakeSocket.instances[0], view }
}

const mount = () => mountView().socket

describe('the pad while a game is suspended', () => {
  it('is blocked while the game is on the screen', () => {
    const socket = mount()
    send(socket, 'game:started', GAME)
    expect(isPlaying()).toBe(true)
  })

  it('comes back the moment the game is suspended', () => {
    const socket = mount()
    send(socket, 'game:started', GAME)
    send(socket, 'game:backgrounded',
         { ...SUSPENDED, state_snapshot: state(null, [SUSPENDED]) })

    expect(isPlaying()).toBe(false)
    expect(useStore.getState().sessionGameKey).toBeNull()
    // And the session is not lost — it is on the bar.
    expect(useStore.getState().backgroundSessions).toEqual([
      { gameKey: 'zelda.iso', systemId: 'dolphin', session: 1, kind: 'game' },
    ])
  })

  it('is blocked again when the game comes back to the screen', () => {
    const socket = mount()
    send(socket, 'game:started', GAME)
    send(socket, 'game:backgrounded',
         { ...SUSPENDED, state_snapshot: state(null, [SUSPENDED]) })
    send(socket, 'game:foregrounded',
         { ...GAME, state_snapshot: state(GAME) })

    expect(isPlaying()).toBe(true)
    expect(useStore.getState().backgroundSessions).toEqual([])
  })
})

describe('the suspend handover', () => {
  it('keeps the theme beat up for 900ms and then clears it', async () => {
    vi.useFakeTimers()
    const socket = mount()
    send(socket, 'game:backgrounded',
         { ...SUSPENDED, state_snapshot: state(null, [SUSPENDED]) })
    expect(useStore.getState().transition).toBe('suspend')

    await act(async () => { await vi.advanceTimersByTimeAsync(899) })
    expect(useStore.getState().transition).toBe('suspend')
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    expect(useStore.getState().transition).toBeNull()
  })

  it('clears an unfinished beat when the websocket owner unmounts', () => {
    vi.useFakeTimers()
    const { socket, view } = mountView()
    send(socket, 'game:backgrounded',
         { ...SUSPENDED, state_snapshot: state(null, [SUSPENDED]) })
    expect(useStore.getState().transition).toBe('suspend')
    view.unmount()
    expect(useStore.getState().transition).toBeNull()
  })
})

describe('a resume that swaps two sessions', () => {
  it('moves both slots from one event, not one and then the other', () => {
    // The reason the events carry a snapshot at all: "run 1 came forward"
    // alone says nothing about what happened to run 2, and a client
    // reconstructing it would drop the session that is still frozen.
    const socket = mount()
    send(socket, 'game:started', APP)
    send(socket, 'game:foregrounded',
         { ...GAME, state_snapshot: state(GAME, [{ ...APP, state: 'background' }]) })

    const s = useStore.getState()
    expect(s.sessionGameKey).toBe('zelda.iso')
    expect(s.backgroundSessions).toEqual([
      { gameKey: 'stremio', systemId: 'stremio', session: 2, kind: 'app' },
    ])
  })
})

describe('a session that ended while nobody was connected', () => {
  it('does not leave a bar offering to resume a game that is gone', async () => {
    vi.stubGlobal('WebSocket', FakeSocket)
    vi.spyOn(api.standby, 'get').mockResolvedValue({ state: 'active' } as never)
    // The box answers "nothing at all" — the suspended game was closed during
    // the outage. Without both slots in the resynchronisation, the bar would
    // still be on screen with a Resume button that 409s forever.
    const ask = vi.spyOn(api.games, 'session').mockResolvedValue({} as never)
    render(<Host />)
    const socket = FakeSocket.instances[0]

    send(socket, 'game:backgrounded',
         { ...SUSPENDED, state_snapshot: state(null, [SUSPENDED]) })
    expect(useStore.getState().backgroundSessions).toHaveLength(1)

    await act(async () => { socket.onopen?.(); await Promise.resolve() })
    expect(ask).toHaveBeenCalled()
    expect(useStore.getState().backgroundSessions).toEqual([])
  })

  it('is restored from the announcement the socket makes on connect', () => {
    const socket = mount()
    send(socket, 'game:running', state(null, [SUSPENDED]))
    expect(useStore.getState().sessionGameKey).toBeNull()
    expect(useStore.getState().backgroundSessions).toHaveLength(1)
  })
})

describe('a suspended session that ends on its own', () => {
  it('leaves the bar without touching what is on the screen', () => {
    // Killed from under us — the OOM killer, or `flatpak kill` from a shell.
    // Its finish belongs to a run that never had the screen, so the game that
    // DOES have it must not be unlocked by it.
    const socket = mount()
    send(socket, 'game:running', state(APP, [SUSPENDED]))
    expect(useStore.getState().sessionGameKey).toBe('stremio')

    send(socket, 'game:finished',
         { game_key: 'zelda.iso', system_id: 'dolphin', session: 1, elapsed: 60 })

    const s = useStore.getState()
    expect(s.backgroundSessions).toEqual([])
    expect(s.sessionGameKey).toBe('stremio')
  })
})

describe('the gesture acknowledgement is not session state', () => {
  it('does not unblock the pad when the suspend was refused', () => {
    // `gp:guide` says "the player pressed Home twice", not "a game stopped".
    // The backend now has a real outcome where it suspends NOTHING — the signal
    // did not land — and it still acknowledges the gesture. Treating that as a
    // finish unblocks the pad over a game that is still running fullscreen,
    // which is the exact fault the session guard exists to prevent.
    const socket = mount()
    send(socket, 'game:started', GAME)
    send(socket, 'gp:guide', { action: 'failed' })

    expect(isPlaying()).toBe(true)
    expect(useStore.getState().sessionGameKey).toBe('zelda.iso')
  })

  it('preserves the screen the game was launched from', () => {
    const socket = mount()
    send(socket, 'game:started', GAME)
    useStore.setState({ screen: 'library' })
    send(socket, 'gp:guide', { action: 'backgrounded' })
    expect(useStore.getState().screen).toBe('library')
  })
})
