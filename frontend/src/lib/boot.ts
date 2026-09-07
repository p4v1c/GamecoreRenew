/**
 * When the interface is worth looking at — decided here, once, for everyone.
 *
 * The shell used to show the dashboard when the boot animation ended, and the
 * boot animation ended on a timer. Two consequences, both reported: on a slow
 * box the home appeared empty and filled in underneath the player's thumb, and
 * on a fast one four seconds of animation were added to a boot that was
 * already over. Electron even had a constant for it — `?splashHold=4000` when
 * the machine had booted recently — which is a number chosen on one machine
 * for every machine.
 *
 * So readiness is a set of facts, and it lives in the host rather than in each
 * theme: a condition every theme defined for itself would be a different
 * condition per theme, and one of them would be a timer.
 *
 *   · `theme`   — the theme resolved, or its fallback took over. Either is an
 *                 answer; only "still asking" is not.
 *   · `systems` — the dashboard's own data settled. An empty list is a valid
 *                 success: a box with no emulator installed is a box whose
 *                 home is ready to say so.
 *   · `painted` — marked here, after the two above, once the browser has been
 *                 given a frame to actually draw. `ready-to-show` is a first
 *                 render, not a first render OF SOMETHING.
 *
 * What is deliberately NOT in the list: the network, the cover art, the
 * metadata scraper, a full ROM scan, the playtime figures, a connected pad.
 * Every one of them can be absent on a perfectly good box, and a boot that
 * waits for something optional is a boot that hangs on a bad afternoon.
 */

export const BOOT_STEPS = ['theme', 'systems', 'painted'] as const
export type BootStep = (typeof BOOT_STEPS)[number]

const done = new Set<BootStep>()
const listeners = new Set<() => void>()
let announced = false
let startedAt = Date.now()
/** Invalidates a frame callback that is already in flight. Only a reset can do
 *  that, and only a test resets — but a stray callback marking `painted` for a
 *  boot that no longer exists is exactly the kind of leak that makes one test
 *  pass because of another. */
let paintToken = 0

/** Marks a step, at most once, and tells whoever is watching. */
export function markBootStep(step: BootStep): void {
  if (done.has(step)) return
  done.add(step)
  if (step !== 'painted' && done.has('theme') && done.has('systems')) schedulePaint()
  listeners.forEach(fn => fn())
  announce()
}

export function bootSteps(): Record<string, boolean> {
  return Object.fromEntries(BOOT_STEPS.map(s => [s, done.has(s)]))
}

export function isBootReady(): boolean {
  return BOOT_STEPS.every(s => done.has(s))
}

export function onBootChange(fn: () => void): () => void {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}

/**
 * Two frames, not one.
 *
 * The first callback runs before the paint that follows the commit; the second
 * runs after it. Announcing on the first is announcing a frame that has been
 * computed and not yet shown — which is precisely the difference between the
 * home being ready and the home being visible.
 */
function schedulePaint(): void {
  const raf = typeof requestAnimationFrame === 'function'
    ? requestAnimationFrame
    : (cb: FrameRequestCallback) => setTimeout(() => cb(0), 16) as unknown as number
  const token = paintToken
  raf(() => raf(() => { if (token === paintToken) markBootStep('painted') }))
}

/** Told to the shell exactly once. Absent outside Electron, which is fine: a
 *  browser tab has nobody to tell. */
function announce(): void {
  if (announced || !isBootReady()) return
  announced = true
  try {
    window.gamecore?.bootReady({ steps: bootSteps(), ms: Date.now() - startedAt })
  } catch { /* the shell went away; the interface is still ready */ }
}

/** Tests only — the set is module state, and a test that inherits another's
 *  boot is a test that proves nothing. */
export function resetBootForTests(): void {
  paintToken += 1
  done.clear()
  listeners.clear()
  announced = false
  startedAt = Date.now()
}

/** What every theme got before a theme could declare its own. */
export const DEFAULT_BOOT_BACKGROUND = '#09090f'

/**
 * The ground everything before the theme's splash is painted on.
 *
 * The shell already knows it: it read the active theme's declared
 * `boot.background` from disk before this bundle existed, and the window has
 * been painting it since before the first document. Reading the same value
 * here is what keeps the whole boot one colour — Shelf boots to paper
 * (#F4F2ED), and a dark cover under its splash was a dark-to-white flash at
 * every start.
 *
 * Validated again on this side, and not out of distrust of the shell: the
 * value crossed a process boundary and ends up in a style attribute, so it is
 * checked where it is used rather than only where it was read.
 */
export function bootBackground(): string {
  const declared = typeof window !== 'undefined' ? window.gamecore?.bootBackground : null
  return typeof declared === 'string' && /^#[0-9a-fA-F]{3,8}$/.test(declared.trim())
    ? declared.trim()
    : DEFAULT_BOOT_BACKGROUND
}
