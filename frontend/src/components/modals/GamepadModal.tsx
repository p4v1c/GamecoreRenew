import { useState, useEffect, useCallback } from 'react'
import { useStore } from '../../store'
import { api, SysInfo, UsbDevice } from '../../api'
import { GP_BTN, onGp, useGamepadState } from '../../hooks/useGamepad'
import { ControllerBattery } from '../TopBar'
import ControllerArt, { ControllerLayout } from './gamepad/ControllerArt'
import DefaultGamepadView from './gamepad/DefaultGamepadView'
import MappingWizard from './gamepad/MappingWizard'
import type { GamepadViewProps } from './gamepad/types'

// Ported from stremio-web's GamepadModal (□ toggles it there too), redrawn
// to match GameCore's palette and its actual button mappings.

/**
 * How long △ must be held on this screen to open the mapping wizard.
 *
 * **The gesture lives here and not in a view, and that is the point.** The
 * wizard was reachable through one button, in `DefaultGamepadView` — and
 * neither shipped theme destructures `onRemap`, so on every box anyone
 * actually runs it was invisible. A view is allowed to make that choice; what
 * it must not be able to do is make the wizard unreachable, because for a pad
 * SDL cannot name it is the only way to make the box usable at all. Owning the
 * gesture in the host fixes the class rather than the two instances.
 *
 * And it had a second lock even when visible: a plain <button>, selectable
 * with a mouse and nothing else. A controller screen reached from a sofa,
 * offering the fix for a broken controller behind a pointer.
 *
 * A HOLD rather than a press, because this screen's rule is that every press
 * is a test and must only light up its counterpart on the diagram — the same
 * reason the wizard itself uses a hold for "this pad does not have that
 * button". △ specifically: the library screen's own △ is guarded by
 * `modalDepth`, so nothing else is listening while this is up.
 */
const REMAP_HOLD_MS = 1000

function detectControllerType(): { type: ControllerLayout; name: string } {
  const gp = navigator.getGamepads?.().find(g => g !== null)
  if (!gp) return { type: 'generic', name: 'No controller detected' }
  const id = gp.id.toLowerCase()
  // Sony vendor id 054c — DualShock / DualSense / generic PlayStation
  if (/sony|playstation|dualsense|dualshock|054c/.test(id)) return { type: 'playstation', name: gp.id }
  // Microsoft vendor id 045e — Xbox / XInput (standard mapping mirrors it)
  if (/xbox|microsoft|xinput|045e/.test(id) || gp.mapping === 'standard') return { type: 'xbox', name: gp.id }
  return { type: 'generic', name: gp.id }
}

const GLYPHS: Record<ControllerLayout, { top: string; right: string; bottom: string; left: string; lb: string; rb: string; menu: string; power: string }> = {
  playstation: { top: '△', right: '○', bottom: '✕', left: '□', lb: 'L1', rb: 'R1', menu: 'Options', power: 'Share' },
  xbox:        { top: 'Y', right: 'B', bottom: 'A', left: 'X', lb: 'LB', rb: 'RB', menu: 'Menu',    power: 'View'  },
  generic:     { top: '△', right: '○', bottom: '✕', left: '□', lb: 'L1', rb: 'R1', menu: 'Options', power: 'Share' },
}

export default function GamepadModal({ onClose, startInWizard = false, view: View = DefaultGamepadView }: {
  onClose: () => void
  /** Open straight into the wizard — the unrecognised-controller toast does. */
  startInWizard?: boolean
  view?: React.ComponentType<GamepadViewProps>
}) {
  const { openModal, closeModal } = useStore()
  const [ctrl, setCtrl] = useState(detectControllerType)
  const [sysInfo, setSysInfo] = useState<SysInfo | null>(null)
  const [usbDevices, setUsbDevices] = useState<UsbDevice[]>([])
  const [wizard, setWizard] = useState(startInWizard)
  // Whether GameCore is still configuring emulators for the connected pad.
  // Asked HERE — this is the screen somebody opens when a controller does not
  // work, and "the pad answers perfectly on the diagram and does nothing in
  // game" is exactly what the switch being off looks like from a sofa.
  const [autoOff, setAutoOff] = useState(false)

  // Live button/axis state — drives the drawing below, frame by frame
  const state = useGamepadState()

  useEffect(() => {
    api.sysinfo().then(setSysInfo).catch(() => {})
    api.controllers.autoconfig().then(a => setAutoOff(!a.enabled)).catch(() => {})
    const refresh = () => setCtrl(detectControllerType())
    const offs = [onGp('gp:connected', refresh), onGp('gp:disconnected', refresh)]

    // Polled, not event-driven, and that is not laziness. gp:connected fires
    // from gamepad_monitor, which only ever sees a device with an evdev node
    // that declares BTN_SOUTH — precisely the devices this list is NOT about.
    // A GameCube adapter emits no event when it is plugged in, so a screen
    // that waited for one would sit on "absent" while the owner plugs the
    // thing in and out in front of it, which is the exact moment this list
    // exists to serve.
    const readDevices = () => api.controllers.devices()
      .then(r => setUsbDevices(r.devices ?? []))
      .catch(() => {})
    readDevices()
    const timer = setInterval(readDevices, 2000)
    return () => { offs.forEach(o => o()); clearInterval(timer) }
  }, [])

  // No button binding here on purpose: on this screen every press is a test and
  // must only light up its counterpart on the pad. ○ does NOT go back, and
  // leaving takes a double □ — see CONTROLLER_CLOSE_MS in App.tsx.
  //
  // The one exception is a HOLD, which no press can be mistaken for. See
  // REMAP_HOLD_MS: it is what makes the wizard reachable at all from a sofa,
  // and reachable in a theme that never draws the button.
  const holdingTop = !!state.pressed[GP_BTN.Y]
  useEffect(() => {
    if (!holdingTop || wizard) return
    const timer = setTimeout(() => setWizard(true), REMAP_HOLD_MS)
    // A boolean dependency on purpose: this component re-renders on every
    // frame the pad moves, and a dependency that changed with it would restart
    // the timer whenever a resting stick jittered — the hold would never
    // complete for anyone holding the pad in their hands.
    return () => clearTimeout(timer)
  }, [holdingTop, wizard])

  const g = GLYPHS[ctrl.type]

  const MAPPINGS: [string, string][] = [
    [`D-Pad / L-stick`, 'Navigate'],
    [g.bottom, 'Select · Play'],
    [g.right, 'Back'],
    [g.top, 'Search games (library)'],
    [g.left, 'This screen'],
    [g.menu, 'Settings'],
    [g.power, 'Power menu'],
    [`${g.lb} / ${g.rb}`, 'Pages · Sorting'],
    ['PS ×2', 'Quit running game'],
  ]

  // Bound here so a view mounts it with no props and cannot mis-wire the pad.
  const Art = useCallback(() => <ControllerArt layout={ctrl.type} state={state} />, [ctrl.type, state])

  // Full frame, over everything, and it owns the pad while it is up: the
  // wizard exists precisely for controllers whose buttons mean nothing yet, so
  // it cannot share a screen with a view that reads them as navigation.
  if (wizard) {
    return <MappingWizard onClose={() => {
      // Came from the toast: leaving the wizard leaves entirely. Dropping the
      // player onto the controller diagram instead would strand them one
      // screen deep with the pad that does not work yet.
      if (startInWizard) { onClose(); return }
      setWizard(false)
      api.sysinfo().then(setSysInfo).catch(() => {})
    }} />
  }

  return (
    <View
      layout={ctrl.type}
      name={sysInfo?.controllers?.[0]?.label || sysInfo?.controllers?.[0]?.name || ctrl.name}
      layoutLabel={
        ctrl.type === 'playstation' ? 'PlayStation layout'
        : ctrl.type === 'xbox' ? 'Xbox layout'
        : 'Standard layout'
      }
      connected={ctrl.name !== 'No controller detected'}
      notice={autoOff && ctrl.name !== 'No controller detected'
        ? 'Automatic setup is off, so this pad is not configured in any '
          + 'emulator. Settings → Controllers turns it back on.'
        : ''}
      controllers={sysInfo?.controllers ?? []}
      usbDevices={usbDevices}
      glyphs={g}
      mappings={MAPPINGS}
      onClose={onClose}
      onRemap={() => setWizard(true)}
      Art={Art}
      Battery={ControllerBattery}
    />
  )
}
