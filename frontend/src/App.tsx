import { useState, useEffect, useRef } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useWebSocket } from './hooks/useWebSocket'
import { useGamepad } from './hooks/useGamepad'
import { onGp } from './hooks/useGamepad'
import { useStore } from './store'
import { api } from './api'

import Splash from './components/Splash'
import TopBar from './components/TopBar'
import HomeScreen from './components/HomeScreen'
import LibraryScreen from './components/LibraryScreen'
import SettingsModal from './components/modals/SettingsModal'
import PowerModal from './components/modals/PowerModal'
import GamepadModal from './components/modals/GamepadModal'
import Toasts from './components/ui/Toasts'
import Screensaver from './components/Screensaver'
import { onWsEvent } from './hooks/useWebSocket'
import { playSound } from './lib/sounds'

// The controller screen only exits on a second □ within this window. A single
// press there is a button test like any other — same idea as the double PS
// press that kills a running game (GUIDE_DOUBLE_PRESS_MS in useGamepad).
const CONTROLLER_CLOSE_MS = 1000

export default function App() {
  const [showSplash, setShowSplash] = useState(true)
  const [showSettings, setShowSettings] = useState(false)
  const [showPower, setShowPower] = useState(false)
  const [showGamepad, setShowGamepad] = useState(false)
  const { screen, sessionGameKey, goHome, setSession } = useStore()

  const sessionRef = useRef(sessionGameKey)
  useEffect(() => { sessionRef.current = sessionGameKey }, [sessionGameKey])

  const splashRef = useRef(showSplash)
  useEffect(() => { splashRef.current = showSplash }, [showSplash])

  const gamepadOpenRef = useRef(showGamepad)
  useEffect(() => { gamepadOpenRef.current = showGamepad }, [showGamepad])
  const lastClosePress = useRef(0)

  useWebSocket()
  useGamepad()

  // Trigger overlay when emulator starts/stops
  useEffect(() => {
    const offStart = onWsEvent('game:started', (d) => {
      window.gamecore?.overlayStart((d as { system_id: string }).system_id)
    })
    const offDone = onWsEvent('game:finished', (d) => {
      window.gamecore?.overlayStop((d as { system_id: string }).system_id)
      setSession(null, null)
    })

    // Sync state with Electron events in case WS is slow or missed
    window.gamecore?.onOverlayHide(() => {
      setSession(null, null)
    })

    return () => { offStart(); offDone() }
  }, [setSession])

  // Global gamepad bindings
  useEffect(() => {
    const offs = [
      // Toggle-close always works; opening is refused while another modal
      // (e.g. the library search keyboard) is on screen — otherwise both
      // sets of gamepad handlers fire on every press.
      onGp('gp:menu', () => { if (!splashRef.current && !useStore.getState().powerPending) setShowSettings(s => s ? false : useStore.getState().modalDepth === 0) }),
      onGp('gp:power', () => { if (!splashRef.current && !useStore.getState().powerPending) setShowPower(s => s ? false : useStore.getState().modalDepth === 0) }),
      // □ / X opens the controller screen on a single press, but closes it only
      // on a double press — every button has to stay free for testing in there.
      onGp('gp:x', () => {
        if (splashRef.current || useStore.getState().powerPending) return

        if (!gamepadOpenRef.current) {
          // The opening press must not count as the first half of a close.
          lastClosePress.current = 0
          setShowGamepad(useStore.getState().modalDepth === 0)
          return
        }

        const now = performance.now()
        if (now - lastClosePress.current <= CONTROLLER_CLOSE_MS) {
          lastClosePress.current = 0
          setShowGamepad(false)
        } else {
          lastClosePress.current = now
        }
      }),
      onGp('gp:guide', async () => {
        if (!sessionRef.current) return
        try { await api.games.kill() } catch {}
        setSession(null, null)
        goHome()
      }),
    ]
    return () => offs.forEach(off => off())
  }, [goHome, setSession])

  const handleLaunchApp = async (system: { id: string; path?: string; args?: string }) => {
    playSound('launch')
    try {
      await api.games.launch(system.id)
      setSession(system.id, system.id)
    } catch (e) {
      console.error('Failed to launch app:', e)
    }
  }

  return (
    <div style={{
      width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column',
      fontFamily: "'Outfit', sans-serif", color: '#fff',
      background: screen === 'home'
        ? 'radial-gradient(ellipse 70% 50% at 50% 30%, rgba(124,58,237,0.07) 0%, transparent 70%), #09090f'
        : '#09090f',
      overflow: 'hidden',
    }}>

      <Screensaver />

      <AnimatePresence>
        {showSplash && <Splash onDone={() => setShowSplash(false)} />}
      </AnimatePresence>

      {/* Mounted from the first frame, behind the opaque splash: systems,
          playtime and game counts are fetched while the boot animation plays,
          so the dashboard is already populated when it fades away (it used to
          mount empty once the splash was gone, then pop in). */}
      <TopBar onSettings={() => setShowSettings(true)} onPower={() => setShowPower(true)} />
      <Toasts />

      {/* Both screens stay mounted at all times — toggled via display:none.
          This prevents the re-mount/re-fetch flash when navigating home from library. */}
      <div style={{ flex: 1, display: screen === 'home' ? 'flex' : 'none', flexDirection: 'column', overflow: 'hidden' }}>
        <HomeScreen onLaunchApp={handleLaunchApp} />
      </div>
      <div style={{ flex: 1, display: screen === 'library' ? 'flex' : 'none', flexDirection: 'column', overflow: 'hidden' }}>
        <LibraryScreen />
      </div>

      <AnimatePresence>
        {showSettings && <SettingsModal key="settings" onClose={() => setShowSettings(false)} />}
      </AnimatePresence>

      <AnimatePresence>
        {showPower && <PowerModal key="power" onClose={() => setShowPower(false)} />}
      </AnimatePresence>

      <AnimatePresence>
        {showGamepad && <GamepadModal key="gamepad" onClose={() => setShowGamepad(false)} />}
      </AnimatePresence>
    </div>
  )
}
