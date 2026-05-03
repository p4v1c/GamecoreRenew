import { useEffect, useRef } from 'react'
import { useStore } from '../store'

const WS_URL = `ws://${window.location.host}/ws`

interface WsEvent {
  event: string
  data: Record<string, unknown>
}

type Handler = (data: Record<string, unknown>) => void

const handlers: Map<string, Set<Handler>> = new Map()

let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

function connect() {
  if (socket && socket.readyState < 2) return

  socket = new WebSocket(WS_URL)

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

    return () => { off1(); off1b(); off2(); off3() }
  }, [])
}
