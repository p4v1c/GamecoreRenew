import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { onWsEvent } from '../hooks/useWebSocket'
import { api } from '../api'

type Stage = 'off' | 'screensaver' | 'sleep'

const ROTATE_MS = 9000

/** Fullscreen standby overlay, driven by backend WS events:
 *  standby:screensaver → cover-art slideshow with clock
 *  standby:sleep       → black (the backend turns the screen off via DPMS;
 *                        black avoids a bright flash before/after)
 *  standby:exit        → hidden
 *  Local mouse/keyboard input also wakes the box (controllers are handled
 *  backend-side through evdev). */
export default function Screensaver() {
  const [stage, setStage] = useState<Stage>('off')
  const [covers, setCovers] = useState<{ url: string; name: string }[]>([])
  const [idx, setIdx] = useState(0)
  const [clock, setClock] = useState('')
  const stageRef = useRef(stage)
  useEffect(() => { stageRef.current = stage }, [stage])

  // WS wiring
  useEffect(() => {
    const offs = [
      onWsEvent('standby:screensaver', () => setStage('screensaver')),
      onWsEvent('standby:sleep', () => setStage('sleep')),
      onWsEvent('standby:exit', () => setStage('off')),
    ]
    return () => offs.forEach(o => o())
  }, [])

  // Local (non-gamepad) input wakes the box too
  useEffect(() => {
    if (stage === 'off') return
    const wake = () => { api.standby.exit().catch(() => {}) }
    window.addEventListener('pointermove', wake)
    window.addEventListener('keydown', wake)
    return () => {
      window.removeEventListener('pointermove', wake)
      window.removeEventListener('keydown', wake)
    }
  }, [stage])

  // Build the slideshow list when the screensaver kicks in
  useEffect(() => {
    if (stage !== 'screensaver' || covers.length > 0) return
    let cancelled = false
    ;(async () => {
      try {
        const systems = await api.systems.list()
        const emus = systems.filter(s => s.kind === 'emulator')
        const lists = await Promise.all(emus.map(s =>
          api.games.list(s.id).then(g => g.map(x => ({
            url: `/api/covers/${s.id}/${encodeURIComponent(x.filename)}`,
            name: x.display_name,
          }))).catch(() => [])
        ))
        const all = lists.flat()
        for (let i = all.length - 1; i > 0; i--) {  // shuffle
          const j = Math.floor(Math.random() * (i + 1))
          ;[all[i], all[j]] = [all[j], all[i]]
        }
        if (!cancelled) setCovers(all.slice(0, 40))
      } catch { /* empty slideshow → clock only */ }
    })()
    return () => { cancelled = true }
  }, [stage, covers.length])

  // Rotate covers + tick the clock
  useEffect(() => {
    if (stage !== 'screensaver') return
    const tick = () => setClock(new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }))
    tick()
    const clockT = setInterval(tick, 10000)
    const rotateT = setInterval(() => setIdx(i => i + 1), ROTATE_MS)
    return () => { clearInterval(clockT); clearInterval(rotateT) }
  }, [stage])

  if (stage === 'off') return null

  const cover = covers.length > 0 ? covers[idx % covers.length] : null

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9500, background: '#000', overflow: 'hidden' }}>
      {stage === 'screensaver' && (
        <>
          <AnimatePresence mode="wait">
            {cover && (
              <motion.div
                key={idx}
                initial={{ opacity: 0, scale: 1.04 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 1.6, ease: 'easeInOut' }}
                style={{
                  position: 'absolute', inset: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexDirection: 'column', gap: 24,
                }}
              >
                <img
                  src={cover.url} alt=""
                  onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                  style={{
                    maxWidth: '38vw', maxHeight: '58vh', borderRadius: 16,
                    boxShadow: '0 30px 90px rgba(0,0,0,0.9)',
                    border: '1px solid rgba(255,255,255,0.08)',
                  }}
                />
                <div style={{ fontSize: 18, color: 'rgba(255,255,255,0.35)', fontWeight: 600 }}>
                  {cover.name}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          <div style={{
            position: 'absolute', top: 48, right: 64,
            fontSize: 64, fontWeight: 200, color: 'rgba(255,255,255,0.5)',
            fontVariantNumeric: 'tabular-nums', letterSpacing: 2,
          }}>
            {clock}
          </div>
          <div style={{
            position: 'absolute', bottom: 36, left: 0, right: 0, textAlign: 'center',
            fontSize: 12, color: 'rgba(255,255,255,0.18)', letterSpacing: 2,
          }}>
            PRESS ANY BUTTON TO WAKE
          </div>
        </>
      )}
    </div>
  )
}
