import type { ComponentType } from 'react'
import type { ControllerLayout } from './ControllerArt'
import type { SysInfo, UsbDevice } from '../../../api'

/**
 * What a controller screen is handed.
 *
 * The live diagram comes ready-made: 300+ lines of SVG wired to the 60 fps pad
 * state, with a layout per controller family. A theme that redrew it would be
 * reimplementing the one thing this screen exists for.
 *
 * Note there are no gamepad bindings to hand over. On this screen every press
 * is a test and must only light up its counterpart — ○ does not go back, and
 * leaving takes a double press of □ (CONTROLLER_CLOSE_MS, in DefaultShell).
 */
export interface GamepadViewProps {
  /** Which family the connected pad belongs to — picks the glyphs and artwork. */
  layout: ControllerLayout
  /** The pad's own name, or "No controller detected". */
  name: string
  /** Human label for the layout, e.g. "PlayStation layout". */
  layoutLabel: string
  connected: boolean
  /**
   * One sentence to draw above the diagram, or empty. Today it says that
   * automatic controller setup is switched off.
   *
   * It belongs on THIS screen because this is where somebody comes when a pad
   * does not work, and the switch produces the most confusing symptom the box
   * has: every button lights up on the diagram, and nothing answers in game.
   * The diagram reads the pad directly through the Gamepad API and would look
   * perfect either way.
   *
   * A view that drops it loses the notice, which is the same trade-off
   * `onRemap` documents below — so both shipped themes draw it. Empty string
   * rather than undefined: a view can render it unconditionally.
   */
  notice?: string
  /** Battery and player index per pad, from the backend registry. */
  controllers: NonNullable<SysInfo['controllers']>
  /**
   * The declared peripherals that take no player slot — a GameCube adapter, a
   * DolphinBar, a wheel. Empty when no installed system declares any, which is
   * the common case and must draw nothing at all.
   *
   * These deliberately do NOT appear among `controllers`: a light gun is not
   * player 2, and giving one a slot is how an emulator ends up writing pad
   * bindings for a device that has no buttons. They are a separate list
   * because they answer a separate question — "is it plugged in".
   */
  usbDevices?: UsbDevice[]
  /** Button glyphs for this family: use these, never hardcoded ✕/○/△/□. */
  glyphs: { top: string; right: string; bottom: string; left: string; lb: string; rb: string; menu: string; power: string }
  /** [key, action] pairs — what each button does across GameCore. */
  mappings: [string, string][]
  onClose: () => void
  /**
   * Open the mapping wizard — map this pad button by button.
   *
   * A view may leave it out; the wizard is then unreachable from that theme,
   * which is a choice a theme is allowed to make. It is NOT optional in the
   * default view: for a pad SDL cannot name, this is the only way to make the
   * box usable at all, and it must not be buried behind a settings tree
   * navigated with the very controller that does not work yet.
   */
  onRemap?: () => void
  /**
   * The live diagram, already bound to the connected pad and its 60 fps state.
   * Mount it with no props — there is nothing for a view to get wrong.
   */
  Art: ComponentType
  /** One battery pill, matching the top bar's. */
  Battery: ComponentType<{ player?: number | null; level: number; charging?: boolean }>
}
