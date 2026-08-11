/**
 * PowerModal — the shutdown flow.
 *
 * The markup lives in a view component, default or themed. What stays here is
 * what must not be reimplemented: the two-press confirmation, the pending lock
 * that makes every close path inert, the failsafe that unfreezes the UI when
 * the OS never powers off, and the mapping scan.
 */
import { useState, useEffect, useRef, useMemo } from 'react'
import { useStore } from '../../store'
import { onGp } from '../../hooks/useGamepad'
import DefaultPowerView from './power/DefaultPowerView'
import type { PowerOption, PowerViewProps } from './power/types'

interface Props {
  onClose: () => void
  view?: React.ComponentType<PowerViewProps>
  /**
   * Ids this theme offers somewhere else, so they can leave this menu.
   *
   * The mapping utilities are here for a historical reason — this modal had the
   * two-press confirmation and no settings screen did — not because saving a
   * pad's controls is a way to end a session. A theme that gives them a proper
   * home says so, and gets the three-row power menu the design asks for.
   *
   * Filtered here rather than in the view, and that distinction is the whole
   * point: `focusIdx` is an index into the array handed over, so a view that
   * hid rows itself would leave the cursor landing on nothing. The array the
   * host counts and the array the player sees have to be the same one.
   */
  omit?: string[]
}

/**
 * What may never leave, whatever a theme claims.
 *
 * Powering off is the one thing a console must always be able to do, and
 * `desktop` is the escape hatch when the front end itself is the problem. A
 * theme with a typo in its omit list must not be able to build a box that
 * cannot be turned off from the sofa.
 */
const UNREMOVABLE = new Set(['restart', 'shutdown', 'desktop'])

const OPTIONS: PowerOption[] = [
  { id: 'scan',     label: 'Scan mapping', busy: 'Scanning…',  icon: '◎', color: '#22c55e', desc: 'Save the connected pad’s controls (3DS/DS/GBA…)' },
  // The inverse of the one above. A saved mapping whose config names a
  // different pad is refused on connect rather than applied, and without this
  // the owner is told their mapping was ignored and can do nothing about it.
  { id: 'forget',   label: 'Forget mapping', busy: 'Forgetting…', icon: '⌫', color: '#64748b', desc: 'Delete the connected pad’s saved controls, then scan again' },
  // Shutdown before restart, which is the order the design asks for and the
  // order of how often each is wanted. It is safe to lead with here because
  // the two mapping utilities sit above it in the unfiltered list, so the
  // cursor still starts on something harmless; a theme that omits them gets
  // Shutdown under the cursor and the two-press confirmation is what stands
  // between that and a powered-off box.
  { id: 'shutdown', label: 'Shutdown', busy: 'Shutting down…', icon: '⏻', color: '#ef4444', desc: 'Power off' },
  { id: 'restart',  label: 'Restart',  busy: 'Restarting…',    icon: '↺', color: '#f59e0b', desc: 'Reboot the system' },
  // Leaving for the desktop is the third way a session ends, and it belonged
  // in the menu the other two are in. It was reachable only from
  // Settings → Desktop, four rows into a menu nobody opens to quit — while the
  // button that means "I am done with this box" opened a screen that could
  // restart it and shut it down but not step out of it.
  //
  // Appended rather than slotted in beside Restart on purpose: `focusIdx`
  // indexes this array, so the first entry is whatever the cursor starts on.
  // Putting a session-ending action there would move the default focus off the
  // harmless mapping scan and onto something two presses from quitting.
  { id: 'desktop',  label: 'Return to desktop', busy: 'Leaving…', icon: '⌘', color: '#38bdf8', desc: 'Leave the front end for the system session' },
]

// If the OS is still alive after this delay the power command failed
// (no sudo rights, systemctl error…) — unfreeze the UI instead of soft-locking.
const POWER_FAILSAFE_MS = 10000

export default function PowerModal({ onClose, view: View = DefaultPowerView, omit }: Props) {
  const options = useMemo(() => {
    const drop = new Set((omit ?? []).filter(id => !UNREMOVABLE.has(id)))
    return drop.size ? OPTIONS.filter(o => !drop.has(o.id)) : OPTIONS
  }, [omit])

  const [confirm, setConfirm] = useState<string | null>(null)
  const [focusIdx, setFocusIdx] = useState(0)
  const [scanning, setScanning] = useState(false)
  const [scanResult, setScanResult] = useState<string | null>(null)
  const { openModal, closeModal, powerPending, setPowerPending } = useStore()

  // Stable refs to avoid stale closure in confirm handler
  // The filtered list, for the handlers: they are bound once and would
  // otherwise keep counting the array as it was when the menu opened.
  const optionsRef = useRef(options)
  useEffect(() => { optionsRef.current = options }, [options])

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
    if (id === 'forget') {
      // Two-press like the power actions — it deletes the owner's saved work —
      // but never powerPending: the OS stays up, so soft-locking the UI until
      // a shutdown that will not come would strand them on this screen.
      if (confirmRef.current !== id) { setConfirm(id); return }
      setConfirm(null)
      setScanning(true); setScanResult(null)
      fetch('/api/controllers/scan-mapping', { method: 'DELETE' })
        .then(r => r.json())
        .then(d => setScanResult(
          d.ok
            ? `Forgot for ${d.controller}: ${d.forgotten?.length ? d.forgotten.join(', ') : 'nothing was saved'}`
            : (d.error || 'forget failed')))
        .catch(() => setScanResult('forget failed'))
        .finally(() => setScanning(false))
      return
    }
    if (confirmRef.current !== id) { setConfirm(id); return }
    setPowerPending(id)
    if (id === 'desktop') {
      // The same two presses and the same pending lock as the two above: this
      // also ends the session, and if the window refuses to go the failsafe is
      // what gives the screen back instead of stranding the player on a menu
      // that has stopped accepting input. Identical to Settings → Desktop,
      // which stays for the sentence of explanation this row has no room for.
      window.gamecore?.quit()
      window.close()
      return
    }
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
      onGp('gp:dpad-down', () => { if (!useStore.getState().powerPending) setFocusIdx(i => Math.min(optionsRef.current.length - 1, i + 1)) }),
      onGp('gp:confirm',   () => {
        const o = optionsRef.current[focusIdxRef.current]
        if (o) handleAction(o.id)
      }),
      onGp('gp:back',  safeClose),
      onGp('gp:power', safeClose),
    ]
    return () => offs.forEach(o => o())
  }, [onClose]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <View
      options={options}
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
