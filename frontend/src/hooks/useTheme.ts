/**
 * Owns the active theme: loads it, hands its surfaces out, and gets out of the
 * way the moment it misbehaves.
 *
 * Three recovery layers, in the order the user meets them:
 *   1. a surface throws  → that surface falls back to the default (ErrorBoundary
 *      in ThemeSurface does this, and calls noteSurfaceCrash below);
 *   2. CRASH_LIMIT crashes → the theme is refused at load and safe mode is set;
 *   3. L1+R1 held         → the default theme is forced from anywhere, even if
 *      nothing renders at all.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  clearThemeStyles, fetchThemeIndex, loadTheme, setActiveTheme,
  type SurfaceMap, type ThemeManifest,
} from '../lib/themeLoader'
import {
  clearCrashes, clearSafeMode, getSafeMode, isBlocked,
  recordCrash, setSafeMode, type SafeModeInfo,
} from '../lib/themeSafety'
import { onGamepadFrame, GP_BTN } from './useGamepad'
import { onWsEvent } from './useWebSocket'

/** How long L1+R1 must be held to force the default theme. */
const RESCUE_HOLD_MS = 2000

/**
 * A theme that has rendered this long without a surface crashing is considered
 * stable, and its crash history is forgotten.
 *
 * Loading the module successfully is NOT that signal: surfaces crash after the
 * module loads, so clearing the counter at load time meant a theme that broke
 * on every boot never reached the limit and looped forever.
 */
const STABLE_AFTER_MS = 20000

export interface ThemeState {
  /** Surfaces to render; empty object means "all default". */
  surfaces: SurfaceMap
  /** Active theme id, or null for the built-in default. */
  themeId: string | null
  manifest: ThemeManifest | null
  loading: boolean
  /** Set when a theme was refused; the settings page shows it. */
  safeMode: SafeModeInfo | null
  /** Remounts boundaries when the theme changes. */
  resetKey: string
  reload: () => void
  select: (id: string | null) => Promise<void>
  noteSurfaceCrash: (surface: string) => void
}

export function useTheme(): ThemeState {
  const [surfaces, setSurfaces] = useState<SurfaceMap>({})
  const [themeId, setThemeId] = useState<string | null>(null)
  const [manifest, setManifest] = useState<ThemeManifest | null>(null)
  const [loading, setLoading] = useState(true)
  const [safeMode, setSafe] = useState<SafeModeInfo | null>(() => getSafeMode())
  const [nonce, setNonce] = useState(0)

  const activeIdRef = useRef<string | null>(null)
  const stableTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const apply = useCallback(async () => {
    setLoading(true)
    try {
      const index = await fetchThemeIndex()
      const id = index.active
      activeIdRef.current = id

      if (!id) {
        clearThemeStyles()
        setSurfaces({}); setThemeId(null); setManifest(null)
        return
      }

      const m = index.themes.find(t => t.id === id) || null
      if (!m) {
        console.warn(`[gamecore] active theme "${id}" is not installed — using default`)
        setSurfaces({}); setThemeId(null); setManifest(null)
        return
      }
      if (!m.compatible) {
        setSafeMode(id, `needs SDK v${m.api}, this build speaks v${index.sdk_version}`)
        setSafe(getSafeMode())
        setSurfaces({}); setThemeId(null); setManifest(m)
        return
      }
      if (isBlocked(id)) {
        setSafeMode(id, 'it crashed repeatedly — loading was refused')
        setSafe(getSafeMode())
        setSurfaces({}); setThemeId(null); setManifest(m)
        return
      }

      const loaded = await loadTheme(m)
      setSurfaces(loaded); setThemeId(id); setManifest(m)
      // Forget older failures only once it has actually stayed up (see above).
      if (stableTimer.current) clearTimeout(stableTimer.current)
      stableTimer.current = setTimeout(() => clearCrashes(id), STABLE_AFTER_MS)
    } catch (e) {
      const id = activeIdRef.current
      const reason = e instanceof Error ? e.message : String(e)
      console.error('[gamecore] theme load failed:', e)
      if (id) {
        recordCrash(id)
        setSafeMode(id, reason)
        setSafe(getSafeMode())
      }
      clearThemeStyles()
      setSurfaces({}); setThemeId(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { apply() }, [apply, nonce])

  useEffect(() => () => { if (stableTimer.current) clearTimeout(stableTimer.current) }, [])

  // Another client (or the settings page) changed the selection.
  useEffect(() => onWsEvent('theme:changed', () => setNonce(n => n + 1)), [])

  // ── Rescue: hold L1+R1 ──────────────────────────────────────────────────────
  useEffect(() => {
    let since = 0
    return onGamepadFrame(gp => {
      const held = !!gp?.buttons?.[GP_BTN.L1]?.pressed && !!gp?.buttons?.[GP_BTN.R1]?.pressed
      if (!held) { since = 0; return }
      const now = performance.now()
      if (!since) { since = now; return }
      if (now - since < RESCUE_HOLD_MS) return
      since = 0
      const id = activeIdRef.current
      if (!id) return   // already on the default theme, nothing to rescue from
      console.warn('[gamecore] rescue combo held — forcing the default theme')
      setSafeMode(id, 'the rescue combo (L1+R1) was held')
      setSafe(getSafeMode())
      setActiveTheme(null).catch(() => {})
      setSurfaces({}); setThemeId(null)
      activeIdRef.current = null
    })
  }, [])

  const noteSurfaceCrash = useCallback((surface: string) => {
    const id = activeIdRef.current
    if (!id) return
    // It is not stable after all — cancel the amnesty.
    if (stableTimer.current) { clearTimeout(stableTimer.current); stableTimer.current = null }
    const n = recordCrash(id)
    console.error(`[gamecore] theme ${id}: surface "${surface}" crashed (${n})`)
  }, [])

  const select = useCallback(async (id: string | null) => {
    // A deliberate pick clears both the block and the safe-mode notice.
    clearSafeMode(); setSafe(null)
    if (id) clearCrashes(id)
    await setActiveTheme(id)
    setNonce(n => n + 1)
  }, [])

  return {
    surfaces, themeId, manifest, loading, safeMode,
    resetKey: `${themeId ?? 'default'}:${nonce}`,
    reload: () => setNonce(n => n + 1),
    select, noteSurfaceCrash,
  }
}
