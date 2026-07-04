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
import { onWsEvent } from './hooks/useWebSocket'

export default function App() {
  const [showSplash, setShowSplash] = useState(true)
  const [showSettings, setShowSettings] = useState(false)
  const [showPower, setShowPower] = useState(false)
  const { screen, sessionGameKey, goHome, setSession } = useStore()

  const sessionRef = useRef(sessionGameKey)
  useEffect(() => { sessionRef.current = sessionGameKey }, [sessionGameKey])

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
      onGp('gp:menu', () => setShowSettings(s => !s)),
      onGp('gp:power', () => setShowPower(s => !s)),
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

      <AnimatePresence>
        {showSplash && <Splash onDone={() => setShowSplash(false)} />}
      </AnimatePresence>

      {!showSplash && (
        <>
          <TopBar onSettings={() => setShowSettings(true)} onPower={() => setShowPower(true)} />

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

        </>
      )}
    </div>
  )
}
