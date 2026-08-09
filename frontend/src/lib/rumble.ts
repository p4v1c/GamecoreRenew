/**
 * Haptics — the Gamepad API's vibration actuator, which the box has never used.
 *
 * Modelled on lib/sounds deliberately, because it is the same problem: the
 * theme supplies the *what*, the input bus keeps the *when*. A theme declares
 * what a confirm feels like; it does not get to decide that a d-pad press is a
 * confirm. One concept, two outputs.
 *
 * The host ships **no** default patterns. That is not an oversight: nothing on
 * this box vibrated before, and turning every d-pad press into a buzz is a
 * change to how the console feels that nobody asked for. The mechanism is here,
 * the table is empty, and a theme fills it in.
 *
 * Nothing here checks whether a game is running, and that is on purpose: this
 * module would have to import `isPlaying` from the input bus, which imports
 * this one. `isPlaying` is the single name for that invariant and it stays
 * that way — the two callers apply it themselves (the bus already suppresses
 * every event during a session, and `sdk.input.rumble` guards explicitly).
 */

const LS_ENABLED = 'gc:rumble'

export const rumbleSettings = {
  get enabled(): boolean { return localStorage.getItem(LS_ENABLED) !== 'off' },
  set enabled(v: boolean) { localStorage.setItem(LS_ENABLED, v ? 'on' : 'off') },
}

/** One burst. `strong` is the low-frequency motor, `weak` the high-frequency one. */
export interface RumbleStep {
  /** Milliseconds. */
  duration: number
  /** 0–1. */
  strong?: number
  /** 0–1. */
  weak?: number
  /** Milliseconds to wait before this step. */
  delay?: number
}

/** A single burst, or a sequence played back to back. */
export type RumblePattern = RumbleStep | RumbleStep[]

// Bounded rather than trusted, for the same reason `launch.ms` is: a theme is
// code its owner installed, but a pad that buzzes for a minute is not a look,
// it is a controller the player wants to throw. Unlike a bad grid this one
// cannot even be seen on screen to be diagnosed.
const MAX_STEP_MS = 1000
const MAX_TOTAL_MS = 3000
const MAX_STEPS = 8

const clamp01 = (v: unknown) =>
  typeof v === 'number' && isFinite(v) ? Math.max(0, Math.min(1, v)) : 0

/**
 * The pad the UI is being driven from — the same one `useGamepad` polls.
 *
 * Feedback for a press has to come back through the thing that was pressed. On
 * a box with two pads connected, buzzing both because we could not tell which
 * one moved the cursor is worse than not buzzing at all.
 */
function activePad(): Gamepad | null {
  if (typeof navigator === 'undefined' || !navigator.getGamepads) return null
  return navigator.getGamepads().find(g => g !== null) ?? null
}

/**
 * Play a pattern on the active pad.
 *
 * Silently does nothing when the player has haptics off, when no pad is
 * connected, or when the pad has no actuator — which is most of them through
 * Chromium. That is the honest default: this is feedback, and feedback that
 * throws when it is unavailable turns a nicety into a crash.
 */
export function rumble(pattern: RumblePattern): void {
  if (!rumbleSettings.enabled) return

  const pad = activePad() as (Gamepad & {
    vibrationActuator?: { playEffect(type: string, params: object): Promise<unknown> }
  }) | null
  const actuator = pad?.vibrationActuator
  if (!actuator?.playEffect) return

  const steps = (Array.isArray(pattern) ? pattern : [pattern]).slice(0, MAX_STEPS)
  let at = 0
  for (const step of steps) {
    if (!step || typeof step !== 'object') continue
    const duration = Math.max(0, Math.min(MAX_STEP_MS, Number(step.duration) || 0))
    if (duration === 0) continue
    at += Math.max(0, Math.min(MAX_STEP_MS, Number(step.delay) || 0))
    if (at + duration > MAX_TOTAL_MS) break
    // playEffect rejects if the pad goes away mid-pattern, and an unhandled
    // rejection in a feedback path is not worth a console full of noise.
    actuator.playEffect('dual-rumble', {
      startDelay: at,
      duration,
      strongMagnitude: clamp01(step.strong),
      weakMagnitude: clamp01(step.weak),
    }).catch(() => {})
    at += duration
  }
}

// ── The theme layer ──────────────────────────────────────────────────────────

/** Per-event patterns. Empty unless a theme filled it in — see the header. */
let themeRumble: Record<string, RumblePattern> = {}

export function setThemeRumble(map: Record<string, RumblePattern>): void {
  themeRumble = { ...map }
}

export function clearThemeRumble(): void {
  themeRumble = {}
}

/**
 * The pattern for a gamepad UI event, or null for the events nobody dressed.
 *
 * Keyed on the event name rather than on a sound-style alias, so a theme can
 * make ○ feel different from ✕ without the host having to invent a vocabulary
 * of feelings first.
 */
export function rumbleForGpEvent(event: string): RumblePattern | null {
  return themeRumble[event] ?? null
}
