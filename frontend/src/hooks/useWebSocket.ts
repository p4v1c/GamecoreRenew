import { useEffect, useRef } from 'react'
import { useStore } from '../store'
import { api } from '../api'

const WS_URL = `ws://${window.location.host}/ws`

interface WsEvent {
  event: string
  data: Record<string, unknown>
}

type Handler = (data: Record<string, unknown>) => void

const handlers: Map<string, Set<Handler>> = new Map()

let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

/**
 * Ask the box what it is doing about power, instead of assuming it is awake.
 *
 * The stage used to be learned from the three `standby:*` events and nothing
 * else, so the front end only knew what happened while it was listening. Two
 * ways that goes wrong, and the input guard makes both of them matter:
 *
 *   · the page reloads while the box is asleep — Chromium restarting is enough
 *     — and comes up believing it is awake, over a panel that is switched off;
 *   · the socket drops while the box is awake and the box then falls asleep.
 *     `standby:sleep` is sent to nobody, and the store stays 'off' for as long
 *     as the socket is down: no overlay, no guard, a live cursor over a dark
 *     television.
 *
 * Called on every open, which is the first connection and every reconnection
 * after it. A request that fails changes nothing: a failed request is not
 * evidence about the box, and guessing either way is worse than waiting for the
 * websocket to say. See standbySync.test.ts.
 */
export async function syncStandby(): Promise<void> {
  try {
    const { state } = await api.standby.get()
    const stage = state === 'sleep' ? 'sleep'
      : state === 'screensaver' ? 'screensaver'
        : state === 'active' ? 'off'
          : null      // a word this build does not know — say nothing
    if (stage) useStore.getState().setStandby(stage)
  } catch { /* the websocket will correct us */ }
}

function connect() {
  if (socket && socket.readyState < 2) return

  socket = new WebSocket(WS_URL)

  socket.onopen = () => { syncStandby() }

  socket.onmessage = (e) => {
    try {
      const msg: WsEvent = JSON.parse(e.data)
      handlers.get(msg.event)?.forEach(h => h(msg.data))
    } catch {}
  }

  socket.onclose = () => {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(connect, 3000)
  }

  socket.onerror = () => {
    socket?.close()
  }
}

export function onWsEvent(event: string, handler: Handler): () => void {
  if (!handlers.has(event)) handlers.set(event, new Set())
  handlers.get(event)!.add(handler)
  return () => handlers.get(event)?.delete(handler)
}

export function useWebSocket() {
  const setSession = useStore(s => s.setSession)
  const goHome = useStore(s => s.goHome)
  const initialized = useRef(false)

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true
    connect()

    const onGameStart = (d: Record<string, unknown>) => {
      setSession(d.game_key as string, d.system_id as string)
    }
    const off1 = onWsEvent('game:started', onGameStart)
    // Sent on reconnect if a game is already running — restores session state
    const off1b = onWsEvent('game:running', onGameStart)
    const off2 = onWsEvent('game:finished', () => {
      setSession(null, null)
    })
    // Backend evdev detected PS/guide button and killed the game
    const off3 = onWsEvent('gp:guide', () => {
      setSession(null, null)
      goHome()
    })

    // Standby, into the store rather than into whatever is drawing the
    // screensaver. The input bus reads it to decide whether a press is a
    // command or a wake, and that has to hold for a theme that draws its own
    // standby screen (Summer) or none at all.
    const setStandby = useStore.getState().setStandby
    const off4 = onWsEvent('standby:screensaver', () => setStandby('screensaver'))
    const off5 = onWsEvent('standby:sleep', () => setStandby('sleep'))
    const off6 = onWsEvent('standby:exit', () => setStandby('off'))

    return () => { off1(); off1b(); off2(); off3(); off4(); off5(); off6() }
  }, [])
}
