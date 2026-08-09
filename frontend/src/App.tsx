import { useState, useEffect, useRef } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useWebSocket, onWsEvent } from './hooks/useWebSocket'
import { useGamepad, onGp } from './hooks/useGamepad'
import { useStore } from './store'
import { api } from './api'

import Splash from './components/Splash'
import ErrorBoundary from './components/ErrorBoundary'
import DefaultShell from './components/DefaultShell'
import { useTheme } from './hooks/useTheme'
import { ThemeProvider, Shell } from './components/ThemeSurface'

/**
 * The kernel.
 *
 * Picking a theme swaps the frontend: this mounts one shell — the theme's, or
 * the default one — and nothing else of the UI. What stays here is what a theme
 * must not be able to take away:
 *
 *   · the input bus and the WebSocket
 *   · the fact that there *is* a splash — a theme may redraw it, not remove it
 *   · gp:guide, the double press that kills a running game
 *   · the emulator overlay handshake with Electron
 *   · the error boundaries and the L1+R1 rescue (see useTheme)
 */
/** Longest a boot animation may hold the screen before we move on regardless. */
const SPLASH_WATCHDOG_MS = 20000

export default function App() {
  const [showSplash, setShowSplash] = useState(true)
  const { goHome, setSession, sessionGameKey } = useStore()

  const sessionRef = useRef(sessionGameKey)
  useEffect(() => { sessionRef.current = sessionGameKey }, [sessionGameKey])

  useWebSocket()
  useGamepad()
  const theme = useTheme()

  /**
   * The boot animation is decided once, and only once the theme has resolved.
   *
   * Reading `theme.splash ?? Splash` on every render mounts the default splash
   * immediately — the theme is still loading, so its splash is undefined — and
   * then swaps in the theme's a moment later, mid-animation. You see both boot
   * animations running over each other.
   *
   * Until the theme answers, the screen is a plain opaque cover: a fraction of
   * a second, and the alternative is the dashboard flashing before the splash.
   */
  const chosenSplash = useRef<React.ComponentType<{ onDone: () => void }> | null>(null)
  if (!chosenSplash.current && !theme.loading) chosenSplash.current = theme.splash ?? Splash
  const SplashC = chosenSplash.current

  // A themed splash decides its own length, but not whether booting ever ends:
  // one that forgets to call onDone would leave the box on its title card for
  // good. The default runs ~4s, plus a cold-boot hold capped at 10s.
  useEffect(() => {
    if (!showSplash) return
    const t = setTimeout(() => {
      console.warn('[gamecore] splash never finished — moving on')
      setShowSplash(false)
    }, SPLASH_WATCHDOG_MS)
    return () => clearTimeout(t)
  }, [showSplash])

  // Emulator overlay: show the bezel when a game starts, hide it when it ends.
  useEffect(() => {
    const offStart = onWsEvent('game:started', (d) => {
      // `game_key` is the ROM filename the launcher recorded, and it is what
      // picks this game's bezel out of a pack. Passing only system_id gets the
      // system bezel for every game, which is the feature not existing.
      const ev = d as { system_id: string; game_key?: string }
      window.gamecore?.overlayStart(ev.system_id, ev.game_key)
    })
    const offDone = onWsEvent('game:finished', (d) => {
      window.gamecore?.overlayStop((d as { system_id: string }).system_id)
      setSession(null, null)
    })
    // Sync state with Electron events in case WS is slow or missed
    window.gamecore?.onOverlayHide(() => setSession(null, null))
    return () => { offStart(); offDone() }
  }, [setSession])

  // The one binding no theme may own: quitting a running game.
  useEffect(() => onGp('gp:guide', async () => {
    if (!sessionRef.current) return
    try { await api.games.kill() } catch {}
    setSession(null, null)
    goHome()
  }), [goHome, setSession])

  return (
    <ThemeProvider value={theme}>
      <Shell fallback={DefaultShell} />

      {/* Above the shell, and outside it. A theme draws its own boot animation
          but cannot remove it, and cannot decide when booting ends: onDone is
          ours, and a theme that never calls it hits the watchdog above.

          "Above" has to be built here, because a theme is forbidden to write a
          z-index (docs/themes/README.md §6 — the shell owns stacking) and being
          later in the DOM is not enough: the shell paints its own layers at
          z-index 1, 400 and 500, and a positive z-index beats a `auto` one
          whatever the source order. A themed splash therefore came up UNDER the
          dashboard — the boot animation visible only in the gaps between the
          system tiles, the wordmark hidden behind them entirely. The default
          Splash never showed it because it sets zIndex 9000 on its own root,
          which is a thing only the host is allowed to do.

          So the host supplies the layer and the theme keeps drawing inside it,
          with no rule bent on either side. Same 9000 as the default splash: the
          two are mutually exclusive, and matching keeps one number to change. */}
      <AnimatePresence>
        {showSplash && (SplashC ? (
          <div key="splash" style={{ position: 'fixed', inset: 0, zIndex: 9000 }}>
            <ErrorBoundary resetKey={theme.resetKey} fallback={<Splash onDone={() => setShowSplash(false)} />}>
              <SplashC onDone={() => setShowSplash(false)} />
            </ErrorBoundary>
          </div>
        ) : (
          <div key="pre-splash" style={{ position: 'fixed', inset: 0, zIndex: 900, background: '#09090f' }} />
        ))}
      </AnimatePresence>
    </ThemeProvider>
  )
}
