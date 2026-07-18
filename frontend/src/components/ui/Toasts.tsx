import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { onWsEvent } from '../../hooks/useWebSocket'

interface Toast {
  id: number
  icon: string
  title: string
  body: string
  accent: string
}

const TOAST_MS = 10000

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
    }, TOAST_MS))
  }

  useEffect(() => {
    const off = onWsEvent('gp:battery', (d) => {
      const level = d.level as number
      // One single path everywhere: the native always-on-top HUD window shows
      // over the menu, fullscreen emulators, apps (Stremio…) and bezels alike.
      // The in-app toast is only the fallback for plain-browser access
      // (dev / remote), where the Electron bridge doesn't exist.
      if (window.gamecore?.batteryToast) {
        window.gamecore.batteryToast({ level })
        return
      }
      push({
        icon: '🎮',
        title: 'Controller battery low',
        body: `Your controller has ${level}% battery left`,
        accent: level <= 5 ? '#ef4444' : '#fbbf24',
      })
    })
    const timersMap = timers.current
    return () => {
      off()
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
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
