import type { ComponentType } from 'react'
import type { SysInfo, UsbDevice } from '../../../api'
import type { PadInfo, PadStatus } from '../../../lib/padLayout'

/** Pre-SDK 9 family names. Always 'generic' now: the diagram is universal. */
export type ControllerLayout = 'playstation' | 'xbox' | 'generic'

export type PadPos = 'north' | 'east' | 'south' | 'west'

/** One legend row: a face position, or a named key, and what it does. */
export interface PadAction { pos?: PadPos; label?: string; keys?: string[]; action: string }

/**
 * What a controller screen is handed.
 *
 * The live diagram comes ready-made: the standard layout by position, wired to
 * the 60 fps state of the pad being read, with the controls it lacks drawn
 * absent. A theme that redrew it would be reimplementing the one thing this
 * screen exists for. SDK 9 adds `pads`, `pad`, `status`, `missing`, `actions`
 * and `Position`; the older props stay filled for themes written before it.
 *
 * Note there are no gamepad bindings to hand over. On this screen every press
 * is a test and must only light up its counterpart — ○ does not go back, and
 * leaving takes a double press of □ (CONTROLLER_CLOSE_MS, in DefaultShell).
 */
export interface GamepadViewProps {
  /** SDK 9. Every connected pad, by player; `active` marks the one being read. */
  pads: PadInfo[]
  /** SDK 9. The pad being read: the last one that did something deliberate. */
  pad: PadInfo | null
  /** SDK 9. How well the box knows this pad, or null with no pad. */
  status: PadStatus | null
  /** SDK 9. "Not on this pad: …" for the controls it lacks, or ''. */
  missing: string
  /** SDK 9. A raw pad's buttons by index, held or not; empty for a mapped pad. */
  rawButtons?: boolean[]
  /** SDK 9. The controls it lacks, by name (ls, rs, home, l2…). */
  absent?: string[]
  /** SDK 9. What each position and key does across GameCore. */
  actions: PadAction[]
  /** SDK 9. The legend's position icon: the four face dots, one filled. */
  Position: ComponentType<{ pos: PadPos; size?: number }>
  /** @deprecated since SDK 9: always 'generic'. */
  layout: ControllerLayout
  /** The pad's own name, or "No controller detected". */
  name: string
  /** @deprecated since SDK 9: always "Standard layout". */
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
  /** @deprecated since SDK 9: no longer filled; the controller screen lists pads only. */
  usbDevices?: UsbDevice[]
  /** @deprecated since SDK 9: PlayStation glyphs; use `actions` and `Position`. */
  glyphs: { top: string; right: string; bottom: string; left: string; lb: string; rb: string; menu: string; power: string }
  /** @deprecated since SDK 9: use `actions`. */
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
   * The live diagram, already bound to the pad being read and its 60 fps
   * state. `callouts` letters each part instead of naming it (a manual page).
   */
  Art: ComponentType<{ callouts?: boolean }>
  /** One battery pill, matching the top bar's. */
  Battery: ComponentType<{ player?: number | null; level: number; charging?: boolean }>
}
