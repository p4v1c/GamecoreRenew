import { useState, useEffect, useRef } from 'react'
import { Overlay, OverlayLabel } from '../ui'
import { useStore } from '../../store'
import { onGp } from '../../hooks/useGamepad'

interface Props { onClose: () => void }

const OPTIONS = [
  { id: 'restart',  label: 'Restart',  icon: '↺', color: '#f59e0b', desc: 'Reboot the system' },
  { id: 'shutdown', label: 'Shutdown', icon: '⏻', color: '#ef4444', desc: 'Power off' },
]

export default function PowerModal({ onClose }: Props) {
  const [confirm, setConfirm] = useState<string | null>(null)
  const [focusIdx, setFocusIdx] = useState(0)
  const { openModal, closeModal } = useStore()

  useEffect(() => {
    openModal()
    return () => closeModal()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Stable ref to avoid stale closure in confirm handler
  const focusIdxRef = useRef(focusIdx)
  const confirmRef  = useRef(confirm)
  useEffect(() => { focusIdxRef.current = focusIdx }, [focusIdx])
  useEffect(() => { confirmRef.current  = confirm  }, [confirm])

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-up',   () => setFocusIdx(i => Math.max(0, i - 1))),
      onGp('gp:dpad-down', () => setFocusIdx(i => Math.min(OPTIONS.length - 1, i + 1))),
      onGp('gp:confirm', () => {
        const id = OPTIONS[focusIdxRef.current].id
        if (confirmRef.current !== id) {
          setConfirm(id)
          return
        }
        if (window.gamecore) {
          if (id === 'restart')  window.gamecore.reboot()
          if (id === 'shutdown') window.gamecore.shutdown()
        }
        onClose()
      }),
      onGp('gp:back',  onClose),
      onGp('gp:power', onClose),
    ]
    return () => offs.forEach(o => o())
  }, [onClose])

  const handleAction = (id: string) => {
    if (confirm !== id) { setConfirm(id); return }
    if (window.gamecore) {
      if (id === 'restart')  window.gamecore.reboot()
      if (id === 'shutdown') window.gamecore.shutdown()
    }
    onClose()
  }

  return (
    <Overlay onClose={onClose} width={340}>
      <OverlayLabel text="SYSTEM" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {OPTIONS.map((o, idx) => (
          <div key={o.id} onClick={() => handleAction(o.id)} style={{
            display: 'flex', alignItems: 'center', gap: 16, padding: '16px 18px',
            borderRadius: 14, cursor: 'pointer',
            background: idx === focusIdx
              ? `${o.color}22`
              : confirm === o.id ? `${o.color}18` : 'rgba(255,255,255,0.04)',
            border: idx === focusIdx
              ? `1px solid ${o.color}90`
              : confirm === o.id ? `1px solid ${o.color}70` : '1px solid rgba(255,255,255,0.07)',
            transition: 'all 0.2s',
          }}>
            <div style={{ width: 44, height: 44, borderRadius: 12, background: `${o.color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: o.color }}>
              {o.icon}
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, color: '#fff' }}>
                {confirm === o.id ? `Confirm ${o.label}?` : o.label}
              </div>
              <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>{o.desc}</div>
            </div>
          </div>
        ))}
        <div onClick={onClose} style={{
          padding: '13px 18px', borderRadius: 14, cursor: 'pointer',
          background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
          color: 'rgba(255,255,255,0.4)', fontSize: 14, fontWeight: 500, textAlign: 'center', marginTop: 4,
        }}>Cancel</div>
      </div>
      <div style={{ marginTop: 12, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        ↑↓ Navigate · ✕ Select · ○ Cancel
      </div>
    </Overlay>
  )
}
