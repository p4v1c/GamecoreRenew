/**
 * PowerModal — the shutdown flow.
 *
 * The markup lives in a view component, default or themed. What stays here is
 * what must not be reimplemented: the two-press confirmation, the pending lock
 * that makes every close path inert, and the failsafe that unfreezes the UI
 * when the OS never powers off.
 */
import { useState, useEffect, useRef } from 'react'
import { useStore } from '../../store'
import { onGp } from '../../hooks/useGamepad'
import DefaultPowerView from './power/DefaultPowerView'
import { useSharedPowerView } from './power/useSharedPowerView'
import type { PowerOption, PowerViewProps } from './power/types'

interface Props {
  onClose: () => void
  view?: React.ComponentType<PowerViewProps>
}

/**
 * The three ways a session ends, and nothing else.
 *
 * There is no longer any way for a theme to take a row out. `omit` existed so
 * themes could move "Scan mapping" and "Forget mapping" to their Controllers
 * screen; both actions were removed, and what is left — shutdown, restart,
 * desktop — is exactly the set no theme was ever allowed to drop.
 */
const OPTIONS: PowerOption[] = [
  // Shutdown before restart, which is the order the design asks for and the
  // order of how often each is wanted. It leads, so the cursor opens on it:
  // the two-press confirmation is what stands between that and a
  // powered-off box, and it is the same for every row here.
  { id: 'shutdown', label: 'Shutdown', busy: 'Shutting down…', icon: '⏻', color: 'var(--set-danger, #ef4444)', desc: 'Power off' },
  { id: 'restart',  label: 'Restart',  busy: 'Restarting…',    icon: '↺', color: 'var(--set-warn, #f59e0b)', desc: 'Reboot the system' },
  // Leaving for the desktop is the third way a session ends, and it belonged
  // in the menu the other two are in. It was reachable only from
  // Settings → Desktop, four rows into a menu nobody opens to quit — while the
  // button that means "I am done with this box" opened a screen that could
  // restart it and shut it down but not step out of it.
  //
  // Last on purpose: leaving the front end is the least common of the three.
  { id: 'desktop',  label: 'Return to desktop', busy: 'Leaving…', icon: '⌘', color: 'var(--set-info, #38bdf8)', desc: 'Leave the front end for the system session' },
]

// If the OS is still alive after this delay the power command failed
// (no sudo rights, systemctl error…) — unfreeze the UI instead of soft-locking.
const POWER_FAILSAFE_MS = 10000

export default function PowerModal({ onClose, view }: Props) {
  /**
   * The shared power menu — the same one both themes draw — in the built-in
   * UI's colours, unless a theme passed its own view.
   *
   * `DefaultPowerView` is still the fallback under it, and not as dead code:
   * the shared view is built from an sdk, and if building one ever throws, a
   * box must still be able to turn itself off. That is the one screen where
   * "render nothing" is not an acceptable outcome.
   */
  const Shared = useSharedPowerView()
  const View = view ?? Shared ?? DefaultPowerView
  const options = OPTIONS

  const [confirm, setConfirm] = useState<string | null>(null)
  const [focusIdx, setFocusIdx] = useState(0)
  const { powerPending, setPowerPending } = useStore()

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
    if (useStore.getState().powerPending) return
    if (confirmRef.current !== id) { setConfirm(id); return }
    setPowerPending(id)
    if (id === 'desktop') {
      // The same two presses and the same pending lock as the other two: this
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
      onGp('gp:dpad-down', () => { if (!useStore.getState().powerPending) setFocusIdx(i => Math.min(options.length - 1, i + 1)) }),
      onGp('gp:confirm',   () => {
        const o = options[focusIdxRef.current]
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
      onFocus={setFocusIdx}
      onActivate={handleAction}
      onCancel={safeClose}
    />
  )
}
