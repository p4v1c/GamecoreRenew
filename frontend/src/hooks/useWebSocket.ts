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

/**
 * Which session answer is still worth writing.
 *
 * Bumped by every event that decides the session and read either side of the
 * request below. A `game:started` that arrives while `/api/games/session` is in
 * flight wins: the reply describes the box a moment ago, and clearing a game
 * that has just started would unblock the pad over a running emulator.
 */
let sessionEpoch = 0

/**
 * Which run the store's session belongs to, as the backend numbers them.
 *
 * The backend can have two of them alive at once for a moment — a watcher
 * suspended on a game that has exited, a new game already started — and the
 * late `game:finished` of the first one used to unlock the screen over the
 * second. `null` means an optimistic session written by the launch itself,
 * before any event has named a number: nothing to compare, so nothing is
 * refused.
 */
let currentSession: number | null = null

const writeSession = (gameKey: string | null, systemId: string | null,
                      session: number | null = null) => {
  sessionEpoch += 1
  currentSession = gameKey ? session : null
  useStore.getState().setSession(gameKey, systemId)
}

/**
 * Ask the box what it is running, instead of assuming nothing has changed.
 *
 * The socket carries `game:started` and `game:finished`, so a front end only
 * knows what happened while it was listening. Lose the socket with a game up,
 * have the emulator quit during the outage, come back: the finish was sent to
 * nobody. The reconnect used to resynchronise standby and not the session, so
 * the store kept a game key that no longer existed anywhere, and the session
 * guard blocked the pad on every screen.
 *
 * The socket now announces the session on connect — the empty one too — and
 * this is the second answer to the same question, for the case where that
 * announcement is itself lost. A failed request changes nothing.
 */
export async function syncSession(): Promise<void> {
  const epoch = sessionEpoch
  try {
    const s = await api.games.session()
    if (epoch !== sessionEpoch) return   // an event has since said better
    const key = typeof s?.game_key === 'string' ? s.game_key : null
    writeSession(key, key ? (s.system_id ?? null) : null,
                 typeof s?.session === 'number' ? s.session : null)
  } catch { /* the websocket will correct us */ }
}

function connect() {
  if (socket && socket.readyState < 2) return

  socket = new WebSocket(WS_URL)

  socket.onopen = () => { syncStandby(); syncSession() }

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
  const goHome = useStore(s => s.goHome)
  const initialized = useRef(false)

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true
    connect()

    const runNumber = (d: Record<string, unknown>) =>
      typeof d.session === 'number' ? d.session : null
    const off1 = onWsEvent('game:started', (d) => {
      writeSession(d.game_key as string, d.system_id as string, runNumber(d))
    })
    // Sent on every connection: the session as the backend has it, which is
    // `{}` when there is none. An empty one is an answer — see backend/ws.py.
    const off1b = onWsEvent('game:running', (d) => {
      const key = typeof d.game_key === 'string' ? d.game_key : null
      writeSession(key, key ? (d.system_id as string) : null, runNumber(d))
    })
    const off2 = onWsEvent('game:finished', (d) => {
      // A finish from a run that is already over: the player has started
      // something else since, and this would unlock the screen underneath it.
      const ended = runNumber(d)
      if (ended !== null && currentSession !== null && ended !== currentSession) return
      writeSession(null, null)
    })
    // Backend evdev detected PS/guide button and killed the game
    const off3 = onWsEvent('gp:guide', () => {
      writeSession(null, null)
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
