/**
 * What the controller screen draws, decided from the live pad and the roster.
 *
 * Every pad is drawn as the standard layout, by POSITION (south, east, west,
 * north), so a DualSense, an Xbox pad and a Switch Pro are right by
 * construction. What changes per pad is which controls exist and how honest
 * the screen can be about the mapping.
 */
import type { GamepadState } from '../hooks/useGamepad'
import type { RosterPad } from '../api'

/** Every control the diagram knows, in the W3C standard-mapping order. */
export const CONTROLS = ['south', 'east', 'west', 'north', 'l1', 'r1', 'l2', 'r2',
  'select', 'start', 'l3', 'r3', 'up', 'down', 'left', 'right', 'home'] as const
export type Control = typeof CONTROLS[number] | 'ls' | 'rs'

const FULL: ReadonlySet<string> = new Set([...CONTROLS, 'ls', 'rs'])

export interface PadInfo {
  /** Gamepad.index in the browser, -1 for a pad only the backend sees. */
  index: number
  player: number | null
  name: string
  connection: string
  battery: number | null
  charging: boolean
  known: RosterPad['known'] | null
  /** The browser gives raw buttons: positions on the drawing would lie. */
  raw: boolean
  active: boolean
}

export interface PadStatus { tone: 'ok' | 'warn'; text: string }

/** "Vendor: 054c Product: 09cc" in a Linux Gamepad.id, lowercased. */
export function vidPid(id: string): string | null {
  const m = /Vendor: ([0-9a-f]{4}) Product: ([0-9a-f]{4})/i.exec(id)
  return m ? `${m[1]}:${m[2]}`.toLowerCase() : null
}

/**
 * The roster entry for each browser pad, matched by vendor:product.
 * ponytail: two identical pads pair up in index order; the browser gives no
 * serial, so a swap between them is invisible until a slot-aware id exists.
 */
export function matchRoster(pads: readonly Gamepad[], roster: readonly RosterPad[]): Map<number, RosterPad> {
  const left = [...roster]
  const out = new Map<number, RosterPad>()
  for (const gp of [...pads].sort((a, b) => a.index - b.index)) {
    const key = vidPid(gp.id)
    const i = left.findIndex(r => `${r.vendor}:${r.product}` === key)
    if (i >= 0) out.set(gp.index, left.splice(i, 1)[0])
  }
  return out
}

/** Controls the pad has: its SDL mapping when known, else what the browser reports. */
export function presentControls(state: GamepadState, entry: RosterPad | undefined): ReadonlySet<string> {
  if (entry?.controls) {
    const has = new Set<string>(entry.controls)
    // SDL names sticks by axis; their clicks come with them.
    if (has.has('ls')) has.add('l3')
    if (has.has('rs')) has.add('r3')
    return has
  }
  if (state.mapping !== 'standard') return FULL
  const has = new Set(FULL)
  if (state.pressed.length < 17) has.delete('home')
  return has
}

/** Which controls are held right now, by name. */
export function pressedControls(state: GamepadState): Record<string, boolean> {
  const out: Record<string, boolean> = {}
  CONTROLS.forEach((c, i) => { if (state.pressed[i]) out[c] = true })
  return out
}

const MISSING_NAMES: [string, string][] = [
  ['ls', 'left stick'], ['rs', 'right stick'], ['home', 'Home'],
  ['l2', 'L2'], ['r2', 'R2'], ['select', 'Select'],
]

/** One sentence naming what this pad lacks, or ''. */
export function missingSentence(has: ReadonlySet<string>, analogTriggers: boolean): string {
  const gone = MISSING_NAMES.filter(([k]) => !has.has(k)).map(([, n]) => n)
  const parts = gone.length ? [`Not on this pad: ${gone.join(', ')}.`] : []
  if (!analogTriggers && has.has('l2')) parts.push('Triggers are buttons, not analog.')
  return parts.join(' ')
}

/** The honest one-liner about how well the box knows this pad. */
export function padStatus(pad: PadInfo | null): PadStatus | null {
  if (!pad) return null
  if (pad.raw) return { tone: 'warn', text: 'This pad sends raw buttons, so the drawing cannot place them yet.' }
  switch (pad.known) {
    case 'sdl': return { tone: 'ok', text: 'Recognised. Emulators set it up on their own.' }
    case 'table': return { tone: 'ok', text: 'Recognised from GameCore’s list of known pads.' }
    case 'mapped': return { tone: 'ok', text: 'Mapped on this box.' }
    case 'unknown': return { tone: 'warn', text: 'Not recognised. Emulators that look pads up by name will skip it.' }
    default: return null
  }
}

/** Browser pads and roster rows as one list, the pad being read marked. */
export function buildPads(browser: readonly Gamepad[], roster: readonly RosterPad[], activeIndex: number): PadInfo[] {
  const matched = matchRoster(browser, roster)
  const rows: PadInfo[] = browser.map(gp => {
    const r = matched.get(gp.index)
    return {
      index: gp.index, player: r?.player ?? null, name: r?.name ?? gp.id.replace(/\s*\(.*$/, ''),
      connection: r?.connection ?? '', battery: r?.battery ?? null, charging: r?.charging ?? false,
      known: r?.known ?? null, raw: gp.mapping !== 'standard', active: gp.index === activeIndex,
    }
  })
  return rows.sort((a, b) => (a.player ?? 99) - (b.player ?? 99) || a.index - b.index)
}
