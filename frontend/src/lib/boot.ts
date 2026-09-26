/**
 * When the interface is ready to show — decided once, in the host, for every
 * theme (a timer per theme was how boot got both slower and emptier).
 *
 *   theme    resolved, or its fallback took over
 *   systems  the dashboard data settled (an empty list is a success)
 *   painted  a frame drawn after the two above (`ready-to-show` is not that)
 *
 * Deliberately NOT waited for: network, covers, metadata, ROM scan, playtime,
 * a connected pad — all can be absent on a good box.
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
