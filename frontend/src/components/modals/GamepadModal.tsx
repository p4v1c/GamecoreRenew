import { useState, useEffect, useCallback } from 'react'
import { useStore } from '../../store'
import { api, SysInfo, RosterPad } from '../../api'
import { GP_BTN, onGp, useGamepadState } from '../../hooks/useGamepad'
import { ControllerBattery } from '../TopBar'
import PadDiagram, { PadPosition } from './gamepad/PadDiagram'
import DefaultGamepadView from './gamepad/DefaultGamepadView'
import MappingWizard from './gamepad/MappingWizard'
import type { GamepadViewProps, PadAction } from './gamepad/types'
import { buildPads, matchRoster, missingSentence, padStatus, presentControls, pressedControls } from '../../lib/padLayout'

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

// What the buttons do across GameCore, by position. The pad-glyph hints
// elsewhere keep their PlayStation symbols; this screen names positions
// because it is the one place every pad is drawn the same way.
const ACTIONS: PadAction[] = [
  { pos: 'south', label: 'Bottom', action: 'Select and play' },
  { pos: 'east', label: 'Right', action: 'Back' },
  { pos: 'north', label: 'Top', action: 'Search the library' },
  { pos: 'west', label: 'Left', action: 'This screen' },
  { keys: ['Start'], action: 'Settings' },
  { keys: ['Select'], action: 'Power menu' },
  { keys: ['L1', 'R1'], action: 'Pages and sorting' },
  { keys: ['Home ×2'], action: 'Suspend the game' },
]

// Kept for themes written before SDK 9, which read `glyphs` and `mappings`.
const LEGACY_GLYPHS = { top: '△', right: '○', bottom: '✕', left: '□', lb: 'L1', rb: 'R1', menu: 'Options', power: 'Share' }
const LEGACY_MAPPINGS: [string, string][] = [
  ['D-Pad / L-stick', 'Navigate'], ['✕', 'Select and play'], ['○', 'Back'],
  ['△', 'Search games (library)'], ['□', 'This screen'], ['Options', 'Settings'],
  ['Share', 'Power menu'], ['L1 / R1', 'Pages and sorting'], ['PS ×2', 'Quit running game'],
]

export default function GamepadModal({ onClose, startInWizard = false, view: View = DefaultGamepadView }: {
  onClose: () => void
  /** Open straight into the wizard — the unrecognised-controller toast does. */
  startInWizard?: boolean
  view?: React.ComponentType<GamepadViewProps>
}) {
  const { openModal, closeModal } = useStore()
  const [roster, setRoster] = useState<RosterPad[]>([])
  const [sysInfo, setSysInfo] = useState<SysInfo | null>(null)
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
    const readRoster = () => api.controllers.pads().then(r => setRoster(r.pads ?? [])).catch(() => {})
    const offs = [onGp('gp:connected', readRoster), onGp('gp:disconnected', readRoster)]

    // Polled as well as on the events: the backend's scan lags the browser's
    // connect event by up to one pass, so a single read on the event misses it.
    const readAll = readRoster
    readAll()
    const timer = setInterval(readAll, 2000)
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

  // The pad being read is the one the bus obeys: the last pad that did
  // something deliberate. Pressing □ on pad 2 therefore opens this screen on
  // pad 2, and touching another pad while it is up switches to that one.
  const browserPads = (navigator.getGamepads?.() ?? []).filter((p): p is Gamepad => p !== null)
  const pads = buildPads(browserPads, roster, state.index)
  const pad = pads.find(p => p.active) ?? null
  const entry = state.connected ? matchRoster(browserPads, roster).get(state.index) : undefined
  const has = presentControls(state, entry)
  const analog = entry?.analogTriggers ?? true
  const raw = !!pad?.raw
  const missing = pad && !raw ? missingSentence(has, analog) : ''

  // Bound here so a view mounts it with no props and cannot mis-wire the pad.
  const Art = useCallback(({ callouts = false }: { callouts?: boolean }) => (
    // A raw pad's indices are not positions: lighting them on the drawing would lie.
    <PadDiagram pressed={raw ? {} : pressedControls(state)} axes={raw ? [0, 0, 0, 0] : state.axes}
      triggers={{ l2: state.values[GP_BTN.L2] ?? 0, r2: state.values[GP_BTN.R2] ?? 0 }}
      has={state.connected ? has : new Set()} digitalTriggers={!analog} callouts={callouts} />
  ), [state, has, analog, raw])

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
      api.controllers.pads().then(r => setRoster(r.pads ?? [])).catch(() => {})
    }} />
  }

  return (
    <View
      pads={pads}
      pad={pad}
      status={padStatus(pad)}
      missing={missing}
      rawButtons={raw ? state.pressed : []}
      absent={pad && !pad.raw ? ['ls', 'rs', 'home', 'l2', 'r2', 'select'].filter(c => !has.has(c)) : []}
      actions={ACTIONS}
      Position={PadPosition}
      layout="generic"
      name={pad?.name ?? 'No controller detected'}
      layoutLabel="Standard layout"
      connected={state.connected}
      notice={autoOff && state.connected
        ? 'Automatic setup is off, so this pad is not configured in any '
          + 'emulator. Settings → Controllers turns it back on.'
        : ''}
      controllers={sysInfo?.controllers ?? []}
      glyphs={LEGACY_GLYPHS}
      mappings={LEGACY_MAPPINGS}
      onClose={onClose}
      onRemap={() => setWizard(true)}
      Art={Art}
      Battery={ControllerBattery}
    />
  )
}
