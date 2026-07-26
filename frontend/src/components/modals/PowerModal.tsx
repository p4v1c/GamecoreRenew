import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { Overlay, OverlayLabel } from '../ui'
import { useStore } from '../../store'
import { onGp } from '../../hooks/useGamepad'

interface Props { onClose: () => void }

const OPTIONS = [
  { id: 'scan',     label: 'Scan mapping', busy: 'Scanning…',  icon: '◎', color: '#22c55e', desc: 'Save the connected pad’s controls (3DS/DS/GBA…)' },
  { id: 'restart',  label: 'Restart',  busy: 'Restarting…',    icon: '↺', color: '#f59e0b', desc: 'Reboot the system' },
  { id: 'shutdown', label: 'Shutdown', busy: 'Shutting down…', icon: '⏻', color: '#ef4444', desc: 'Power off' },
]

// If the OS is still alive after this delay the power command failed
// (no sudo rights, systemctl error…) — unfreeze the UI instead of soft-locking.
const POWER_FAILSAFE_MS = 10000

export default function PowerModal({ onClose }: Props) {
  const [confirm, setConfirm] = useState<string | null>(null)
  const [focusIdx, setFocusIdx] = useState(0)
  const [scanning, setScanning] = useState(false)
  const [scanResult, setScanResult] = useState<string | null>(null)
  const { openModal, closeModal, powerPending, setPowerPending } = useStore()

  // Stable refs to avoid stale closure in confirm handler
  const focusIdxRef = useRef(focusIdx)
  const confirmRef  = useRef(confirm)
  useEffect(() => { focusIdxRef.current = focusIdx }, [focusIdx])
  useEffect(() => { confirmRef.current  = confirm  }, [confirm])

  // Failsafe: re-enable the UI if the system never actually powered off
  useEffect(() => {
    if (!powerPending) return
    const t = setTimeout(() => setPowerPending(null), POWER_FAILSAFE_MS)
    return () => clearTimeout(t)
  }, [powerPending, setPowerPending])

  const handleAction = (id: string) => {
    if (useStore.getState().powerPending || scanning) return
    if (id === 'scan') {
      // Not a power action: snapshot the connected pad's mapping, show the result
      // inline. No confirm, no powerPending (the OS stays up).
      setScanning(true); setScanResult(null)
      fetch('/api/controllers/scan-mapping', { method: 'POST' })
        .then(r => r.json())
        .then(d => setScanResult(
          d.ok ? `Saved for ${d.controller}: ${d.saved?.length ? d.saved.join(', ') : 'nothing found'}`
               : (d.error || 'scan failed')))
        .catch(() => setScanResult('scan failed'))
        .finally(() => setScanning(false))
      return
    }
    if (confirmRef.current !== id) { setConfirm(id); return }
    setPowerPending(id)
    if (window.gamecore) {
      if (id === 'restart')  window.gamecore.reboot()
      if (id === 'shutdown') window.gamecore.shutdown()
    }
    // No onClose() here on purpose: the modal stays up until the OS kills the
    // display, so the UI doesn't flash back to the screen behind it.
  }

  // All close paths are inert while the power command is in flight
  const safeClose = () => { if (!useStore.getState().powerPending) onClose() }

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-up',   () => { if (!useStore.getState().powerPending) setFocusIdx(i => Math.max(0, i - 1)) }),
      onGp('gp:dpad-down', () => { if (!useStore.getState().powerPending) setFocusIdx(i => Math.min(OPTIONS.length - 1, i + 1)) }),
      onGp('gp:confirm',   () => handleAction(OPTIONS[focusIdxRef.current].id)),
      onGp('gp:back',  safeClose),
      onGp('gp:power', safeClose),
    ]
    return () => offs.forEach(o => o())
  }, [onClose]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Overlay onClose={safeClose} width={340}>
      <OverlayLabel text="SYSTEM" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, pointerEvents: powerPending ? 'none' : 'auto' }}>
        {OPTIONS.map((o, idx) => {
          const isPending = powerPending === o.id
          const isScan = o.id === 'scan'
          const busyPulse = isPending || (isScan && scanning)
          const dimmed = powerPending !== null && !isPending
          return (
            <div key={o.id} onClick={() => handleAction(o.id)} style={{
              display: 'flex', alignItems: 'center', gap: 16, padding: '16px 18px',
              borderRadius: 14, cursor: powerPending ? 'default' : 'pointer',
              opacity: dimmed ? 0.25 : 1,
              background: isPending || idx === focusIdx
                ? `${o.color}22`
                : confirm === o.id ? `${o.color}18` : 'rgba(255,255,255,0.04)',
              border: isPending || idx === focusIdx
                ? `1px solid ${o.color}90`
                : confirm === o.id ? `1px solid ${o.color}70` : '1px solid rgba(255,255,255,0.07)',
              transition: 'all 0.2s',
            }}>
              <motion.div
                animate={busyPulse ? { opacity: [1, 0.35, 1] } : { opacity: 1 }}
                transition={busyPulse ? { duration: 1.1, repeat: Infinity, ease: 'easeInOut' } : undefined}
                style={{ width: 44, height: 44, borderRadius: 12, background: `${o.color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: o.color }}
              >
                {o.icon}
              </motion.div>
              <div>
                <div style={{ fontWeight: 600, fontSize: 15, color: '#fff' }}>
                  {isScan ? (scanning ? o.busy : o.label)
                          : isPending ? o.busy : confirm === o.id ? `Confirm ${o.label}?` : o.label}
                </div>
                <div style={{ fontSize: 12, color: isScan && scanResult ? o.color : 'rgba(255,255,255,0.35)', marginTop: 2 }}>
                  {isScan && scanResult ? scanResult : o.desc}
                </div>
              </div>
            </div>
          )
        })}
        <div onClick={safeClose} style={{
          padding: '13px 18px', borderRadius: 14, cursor: powerPending ? 'default' : 'pointer',
          background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
          color: 'rgba(255,255,255,0.4)', fontSize: 14, fontWeight: 500, textAlign: 'center', marginTop: 4,
          opacity: powerPending ? 0.25 : 1,
        }}>Cancel</div>
      </div>
      <div style={{ marginTop: 12, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        {powerPending ? ' ' : '↑↓ Navigate · ✕ Select · ○ Cancel'}
      </div>
    </Overlay>
  )
}
