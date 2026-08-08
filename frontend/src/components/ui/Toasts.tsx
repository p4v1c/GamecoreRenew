import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { onWsEvent } from '../../hooks/useWebSocket'
import { useStore } from '../../store'

interface Toast {
  id: number
  icon: string
  title: string
  body: string
  accent: string
  /** An offer the player can take, drawn as a button inside the toast. */
  action?: { label: string; run: () => void }
}

const TOAST_MS = 10000

/**
 * A toast carrying a button stays up longer.
 *
 * Ten seconds is right for something you only have to read. It is not enough
 * to read an unexpected message, understand that the controller in your hands
 * is the subject, and decide — and this is the one toast whose whole point is
 * that the player acts on it.
 */
const ACTION_TOAST_MS = 30000

let nextId = 1

/** Top-right toast stack. Listens to backend WS events (gp:battery for now)
 *  and shows each notification for 10 s. */
export default function Toasts() {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  const push = (t: Omit<Toast, 'id'>) => {
    const id = nextId++
    setToasts(prev => [...prev, { ...t, id }])
    timers.current.set(id, setTimeout(() => {
      setToasts(prev => prev.filter(x => x.id !== id))
      timers.current.delete(id)
    }, t.action ? ACTION_TOAST_MS : TOAST_MS))
  }

  const dismiss = (id: number) => {
    const timer = timers.current.get(id)
    if (timer) clearTimeout(timer)
    timers.current.delete(id)
    setToasts(prev => prev.filter(x => x.id !== id))
  }

  useEffect(() => {
    // One single path everywhere: the native always-on-top HUD window shows
    // over the menu, fullscreen emulators, apps (Stremio…) and bezels alike.
    // The in-app toast is only the fallback for plain-browser access
    // (dev / remote), where the Electron bridge doesn't exist.
    const offBattery = onWsEvent('gp:battery', (d) => {
      const level = d.level as number
      const player = (d.player ?? null) as number | null
      if (window.gamecore?.batteryToast) {
        window.gamecore.batteryToast({ level, player })
        return
      }
      const who = player ? `Controller ${player}` : 'Controller'
      push({
        icon: '🎮',
        title: `${who} battery low`,
        body: `${who} has ${level}% battery left`,
        accent: level <= 5 ? '#ef4444' : '#fbbf24',
      })
    })

    const onControllerEvent = (connected: boolean) => (d: Record<string, unknown>) => {
      const player = (d.player ?? null) as number | null
      const label = typeof d.label === 'string' ? d.label : ''
      const who = player ? `Controller ${player}` : 'Controller'

      // P1 made the give-up visible in the journal and at "Scan mapping".
      // Neither is where the player is standing: they have just plugged a pad
      // in and it does not work. This is, and it used to say "Controller 2
      // connected" in green for a controller dead in every emulator that
      // matches a device by name.
      //
      // Deliberately NOT handed to the Electron HUD, which every other toast
      // goes to when it exists. The HUD is a native always-on-top window that
      // draws text: it cannot carry a button, and an offer nobody can accept
      // is worse than the silence it replaces — this one stays in-app, where
      // it is clickable and reachable from the pad.
      if (connected && d.unmapped === true) {
        push({
          icon: '🕹️',
          title: `${who} is not recognised`,
          body: `${label || 'This controller'} is not in any controller `
              + 'database, so emulators cannot bind it. Map it once — about a '
              + 'minute, no keyboard.',
          accent: '#fbbf24',
          action: { label: 'Map it now', run: () => useStore.getState().requestRemap() },
        })
        return
      }

      if (window.gamecore?.controllerToast) {
        window.gamecore.controllerToast({ player, label, connected })
        return
      }
      push({
        icon: '🎮',
        title: `${who} ${connected ? 'connected' : 'disconnected'}`,
        body: label,
        accent: connected ? '#4ade80' : '#94a3b8',
      })
    }
    const offConnected = onWsEvent('gp:connected', onControllerEvent(true))
    const offDisconnected = onWsEvent('gp:disconnected', onControllerEvent(false))

    // A launch that never started. Without this the API answered 503 and the
    // loading screen simply stayed up, with nothing on screen saying why.
    const offFailed = onWsEvent('game:failed', (d) => {
      const detail = typeof d.detail === 'string' ? d.detail : ''
      push({
        icon: '⚠️',
        title: 'Could not start the game',
        body: detail || 'The emulator could not be launched',
        accent: '#ef4444',
      })
    })

    const timersMap = timers.current
    return () => {
      offBattery()
      offConnected()
      offDisconnected()
      offFailed()
      timersMap.forEach(clearTimeout)
      timersMap.clear()
    }
  }, [])

  return (
    <div style={{
      position: 'fixed', top: 64, right: 16, zIndex: 100,
      display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'flex-end',
      pointerEvents: 'none',
    }}>
      <AnimatePresence>
        {toasts.map(t => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, x: 60, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 60, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            style={{
              display: 'flex', alignItems: 'center', gap: 12,
              padding: '12px 16px', borderRadius: 12, minWidth: 280, maxWidth: 380,
              background: 'rgba(18,18,26,0.92)', backdropFilter: 'blur(16px)',
              border: `1px solid ${t.accent}40`,
              boxShadow: `0 8px 32px rgba(0,0,0,0.5), 0 0 12px ${t.accent}20`,
              // The stack is click-through so a toast never steals a press
              // from the screen behind it. A toast that OFFERS something has
              // to take that back, or its button is decorative.
              pointerEvents: t.action ? 'auto' : 'none',
            }}
          >
            <div style={{
              width: 36, height: 36, borderRadius: 9, flexShrink: 0,
              background: `${t.accent}20`, display: 'flex',
              alignItems: 'center', justifyContent: 'center', fontSize: 18,
            }}>{t.icon}</div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: t.accent }}>{t.title}</div>
              <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)', marginTop: 2 }}>{t.body}</div>
              {t.action && (
                <button
                  onClick={() => { t.action!.run(); dismiss(t.id) }}
                  style={{
                    marginTop: 8, padding: '5px 12px', borderRadius: 8,
                    background: `${t.accent}22`, border: `1px solid ${t.accent}66`,
                    color: t.accent, fontSize: 12, fontWeight: 700,
                    cursor: 'pointer', font: 'inherit',
                  }}
                >{t.action.label}</button>
              )}
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
