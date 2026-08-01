/**
 * PowerModal — the shutdown flow.
 *
 * The markup lives in a view component, default or themed. What stays here is
 * what must not be reimplemented: the two-press confirmation, the pending lock
 * that makes every close path inert, the failsafe that unfreezes the UI when
 * the OS never powers off, and the mapping scan.
 */
import { useState, useEffect, useRef } from 'react'
import { useStore } from '../../store'
import { onGp } from '../../hooks/useGamepad'
import DefaultPowerView from './power/DefaultPowerView'
import type { PowerOption, PowerViewProps } from './power/types'

interface Props {
  onClose: () => void
  view?: React.ComponentType<PowerViewProps>
}

const OPTIONS: PowerOption[] = [
  { id: 'scan',     label: 'Scan mapping', busy: 'Scanning…',  icon: '◎', color: '#22c55e', desc: 'Save the connected pad’s controls (3DS/DS/GBA…)' },
  { id: 'restart',  label: 'Restart',  busy: 'Restarting…',    icon: '↺', color: '#f59e0b', desc: 'Reboot the system' },
  { id: 'shutdown', label: 'Shutdown', busy: 'Shutting down…', icon: '⏻', color: '#ef4444', desc: 'Power off' },
]

// If the OS is still alive after this delay the power command failed
// (no sudo rights, systemctl error…) — unfreeze the UI instead of soft-locking.
const POWER_FAILSAFE_MS = 10000

export default function PowerModal({ onClose, view: View = DefaultPowerView }: Props) {
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
          d.ok ? [
            `Saved for ${d.controller}: ${d.saved?.length ? d.saved.join(', ') : 'nothing found'}`,
            // An emulator whose config names another controller is refused
            // rather than filed under this pad. Silence there used to let a
            // DualShock 4 mapping be stored as the Xbox pad's.
            d.refused?.length ? `— skipped (configured for another pad): ${d.refused.join(', ')}` : '',
          ].filter(Boolean).join(' ')
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
    <View
      options={OPTIONS}
      focusIdx={focusIdx}
      confirmId={confirm}
      pendingId={powerPending}
      scanning={scanning}
      scanResult={scanResult}
      onFocus={setFocusIdx}
      onActivate={handleAction}
      onCancel={safeClose}
    />
  )
}
