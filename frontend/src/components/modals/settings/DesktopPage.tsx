import { useEffect, useRef } from 'react'
import { Overlay, BackHeader } from '../../ui'
import { onGp } from '../../../hooks/useGamepad'
import { useSubPageGamepad } from './useSubPageGamepad'

export function DesktopPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const exitRef = useRef<() => void>(() => {})

  const doExit = () => { window.gamecore?.quit(); window.close() }
  exitRef.current = doExit

  useSubPageGamepad(onBack, onClose)

  useEffect(() => {
    const off = onGp('gp:confirm', () => exitRef.current())
    return off
  }, [])

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="DESKTOP MODE" onBack={onBack} />
      <div style={{ padding: '20px 22px', borderRadius: 14, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', marginBottom: 24, color: '#fca5a5', fontSize: 15, lineHeight: 1.8 }}>
        Exit GameCore and return to the system desktop environment.
      </div>
      <div onClick={doExit} style={{ padding: 16, borderRadius: 14, cursor: 'pointer', background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)', color: '#fca5a5', fontWeight: 700, textAlign: 'center', fontSize: 16 }}>
        ✕ Exit to Desktop
      </div>
      <div style={{ marginTop: 8, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        ✕ Confirm · ○ Cancel
      </div>
    </Overlay>
  )
}
