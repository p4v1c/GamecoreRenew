/**
 * Safe mode — the part that keeps a broken theme from bricking the box.
 *
 * The active theme is stored server-side (config/theme.json) so it survives a
 * cache wipe. Crash bookkeeping is deliberately client-side: it is about *this*
 * renderer failing to run *this* theme, and it must be readable before any
 * network call so a theme that crashes at load can't loop forever.
 *
 * Recovery paths, in order of how likely the user reaches them:
 *   1. the surface boundary swaps that one screen for the default;
 *   2. after CRASH_LIMIT failures the theme is refused entirely;
 *   3. holding L1+R1 for RESCUE_HOLD_MS forces the default theme, even if
 *      nothing renders — but only in the menu, never while a game is running:
 *      that combo is ordinary play input, and the UI still polls the pad behind
 *      an emulator whose system has no bezel (see the rescue in useTheme).
 */
const KEY_CRASH = 'gc:theme:crashes'
const KEY_SAFE = 'gc:theme:safeMode'

/** Refuse a theme after this many recorded crashes. */
export const CRASH_LIMIT = 2

export interface SafeModeInfo {
  active: boolean
  /** Theme that was refused, so the UI can name it. */
  themeId: string
  reason: string
}

function readCrashes(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(KEY_CRASH) || '{}')
  } catch {
    return {}
  }
}

function writeCrashes(map: Record<string, number>): void {
  try {
    localStorage.setItem(KEY_CRASH, JSON.stringify(map))
  } catch {
    /* private mode / quota — safe mode degrades to "no memory", not to a crash */
  }
}

export function crashCount(themeId: string): number {
  return readCrashes()[themeId] || 0
}

export function recordCrash(themeId: string): number {
  const map = readCrashes()
  map[themeId] = (map[themeId] || 0) + 1
  writeCrashes(map)
  return map[themeId]
}

/** Called when a theme renders cleanly, so an old failure doesn't haunt it forever. */
export function clearCrashes(themeId: string): void {
  const map = readCrashes()
  if (map[themeId]) {
    delete map[themeId]
    writeCrashes(map)
  }
}

export function isBlocked(themeId: string): boolean {
  return crashCount(themeId) >= CRASH_LIMIT
}

export function getSafeMode(): SafeModeInfo | null {
  try {
    const raw = localStorage.getItem(KEY_SAFE)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setSafeMode(themeId: string, reason: string): void {
  try {
    localStorage.setItem(KEY_SAFE, JSON.stringify({ active: true, themeId, reason }))
  } catch { /* ignore */ }
}

/** Cleared when the user deliberately picks a theme again. */
export function clearSafeMode(): void {
  try {
    localStorage.removeItem(KEY_SAFE)
  } catch { /* ignore */ }
}
