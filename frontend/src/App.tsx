import { useState, useEffect, useRef } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useWebSocket, onWsEvent } from './hooks/useWebSocket'
import { useGamepad, onGp } from './hooks/useGamepad'
import { useStore } from './store'
import { api } from './api'

import Splash from './components/Splash'
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
 *   · the splash, so a theme that ships none still gets one
 *   · gp:guide, the double press that kills a running game
 *   · the emulator overlay handshake with Electron
 *   · the error boundaries and the L1+R1 rescue (see useTheme)
 */
export default function App() {
  const [showSplash, setShowSplash] = useState(true)
  const { goHome, setSession, sessionGameKey } = useStore()

  const sessionRef = useRef(sessionGameKey)
  useEffect(() => { sessionRef.current = sessionGameKey }, [sessionGameKey])

  useWebSocket()
  useGamepad()
  const theme = useTheme()

  // Emulator overlay: show the bezel when a game starts, hide it when it ends.
  useEffect(() => {
    const offStart = onWsEvent('game:started', (d) => {
      window.gamecore?.overlayStart((d as { system_id: string }).system_id)
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

      {/* Above the shell, and outside it: a theme cannot remove the boot
          animation, and one that ships no splash still gets this one. */}
      <AnimatePresence>
        {showSplash && <Splash onDone={() => setShowSplash(false)} />}
      </AnimatePresence>
    </ThemeProvider>
  )
}
