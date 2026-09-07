/**
 * Finding out whether a game is still running, rather than assuming it is.
 *
 * Same shape as the standby resynchronisation next door, and found by the same
 * reasoning: the front end learned the session from `game:started` and
 * `game:finished`, so it only ever knew what happened while it was listening.
 *
 * Lose the socket with a game up — Chromium reloading is enough, so is the
 * backend restarting — let the emulator quit during the outage, and reconnect.
 * The finish was broadcast to nobody. The store kept `sessionGameKey`, the
 * session guard kept blocking every press, and the only ways out were another
 * game or a reload.
 *
 * Two halves, because either alone still loses the case it does not cover:
 *
 *   · the backend announces the session on every connection, `{}` included —
 *     silence used to mean "no game", which is indistinguishable from a lost
 *     message;
 *   · the client asks over HTTP on open as well, and refuses to write its
 *     answer if an event has spoken since. A reply that describes the box a
 *     moment ago must not clear a game that started while it was in flight.
 */
import { render, act, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useWebSocket, syncSession } from './useWebSocket'
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

afterEach(() => {
  cleanup()
  // The socket is module state, not component state: `connect()` reuses one
  // that still looks open, so the next test would never get an instance of its
  // own. Marked closed by assignment rather than `close()`, which would arm a
  // reconnection three seconds into whatever runs next.
  FakeSocket.instances.forEach(s => { s.onclose = null; s.readyState = 3 })
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers()
  FakeSocket.instances = []
})

describe('a session that ended while nobody was connected', () => {
  it('is let go of when the socket comes back', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('WebSocket', FakeSocket)
    vi.spyOn(api.standby, 'get').mockResolvedValue({ state: 'active' } as never)
    vi.spyOn(api.games, 'session').mockResolvedValue({})
    useStore.setState({ sessionGameKey: null, sessionSystemId: null })

    render(<Host />)
    await act(async () => { FakeSocket.instances[0].onopen?.() })
    await send(FakeSocket.instances[0], 'game:started', { game_key: 'old.rom', system_id: 'gc' })
    expect(useStore.getState().sessionGameKey).toBe('old.rom')

    act(() => FakeSocket.instances[0].close())
    // The emulator quits here. Nobody hears `game:finished`.
    await act(async () => { vi.advanceTimersByTime(3000) })
    await act(async () => { FakeSocket.instances[1].onopen?.() })
    expect(useStore.getState().sessionGameKey).toBeNull()
  })

  it('is let go of on the announcement alone, without the HTTP answer', async () => {
    vi.stubGlobal('WebSocket', FakeSocket)
    vi.spyOn(api.standby, 'get').mockRejectedValue(new Error('offline'))
    vi.spyOn(api.games, 'session').mockRejectedValue(new Error('offline'))
    useStore.setState({ sessionGameKey: 'old.rom', sessionSystemId: 'gc' })

    render(<Host />)
    await act(async () => { FakeSocket.instances[0].onopen?.() })
    // What `ws.connect()` sends when nothing is running.
    await send(FakeSocket.instances[0], 'game:running', {})
    expect(useStore.getState().sessionGameKey).toBeNull()
  })

  it('still restores a game that is genuinely running', async () => {
    vi.stubGlobal('WebSocket', FakeSocket)
    vi.spyOn(api.standby, 'get').mockRejectedValue(new Error('offline'))
    vi.spyOn(api.games, 'session').mockRejectedValue(new Error('offline'))
    useStore.setState({ sessionGameKey: null, sessionSystemId: null })

    render(<Host />)
    await act(async () => { FakeSocket.instances[0].onopen?.() })
    await send(FakeSocket.instances[0], 'game:running', { game_key: 'live.iso', system_id: 'ps2' })
    expect(useStore.getState().sessionGameKey).toBe('live.iso')
    expect(useStore.getState().sessionSystemId).toBe('ps2')
  })
})

describe('the HTTP answer and the events it may not overrule', () => {
  it('does not clear a game that started while it was in flight', async () => {
    vi.stubGlobal('WebSocket', FakeSocket)
    vi.spyOn(api.standby, 'get').mockRejectedValue(new Error('offline'))
    let answer!: (v: { game_key?: string }) => void
    vi.spyOn(api.games, 'session').mockReturnValue(new Promise(r => { answer = r }))
    useStore.setState({ sessionGameKey: null, sessionSystemId: null })

    render(<Host />)
    await act(async () => { FakeSocket.instances[0].onopen?.() })   // request sent, unanswered
    await send(FakeSocket.instances[0], 'game:started', { game_key: 'new.rom', system_id: 'gc' })
    await act(async () => { answer({}); await Promise.resolve() })
    expect(useStore.getState().sessionGameKey).toBe('new.rom')
  })

  it('says nothing rather than something wrong when the box does not answer', async () => {
    vi.spyOn(api.games, 'session').mockRejectedValue(new Error('offline'))
    useStore.setState({ sessionGameKey: 'live.iso', sessionSystemId: 'ps2' })
    await syncSession()
    expect(useStore.getState().sessionGameKey).toBe('live.iso')
  })
})
