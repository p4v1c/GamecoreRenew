import { useState, useEffect, useRef } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useStore } from '../store'
import { onGp } from '../hooks/useGamepad'

import TopBar from './TopBar'
import HomeScreen from './HomeScreen'
import LibraryScreen from './LibraryScreen'
import SettingsModal from './modals/SettingsModal'
import PowerModal from './modals/PowerModal'
import GamepadModal from './modals/GamepadModal'
import Screensaver from './Screensaver'
import Toasts from './ui/Toasts'
import { launchApp } from './defaults'

/**
 * The default frontend, as one component.
 *
 * A theme replaces this whole thing — that is the model: picking a theme swaps
 * the frontend, and anything it does not provide (the splash, the rescue combo,
 * the input bus) stays with the kernel in App.tsx.
 *
 * It also takes overrides, so "I only want a different dashboard" does not mean
 * "reimplement the launcher": a theme renders this shell and passes `home`.
 * Either way the theme owns one tree, which is what keeps its layers from
 * fighting the host's.
 */

/** The controller screen only exits on a second □ within this window. */
const CONTROLLER_CLOSE_MS = 1000

export interface ShellParts {
  background?: React.ComponentType
  decor?: React.ComponentType
  screensaver?: React.ComponentType
  topbar?: React.ComponentType<{ onSettings: () => void; onPower: () => void }>
  home?: React.ComponentType
  library?: React.ComponentType
  settings?: React.ComponentType<{ onClose: () => void }>
  powerModal?: React.ComponentType<{ onClose: () => void }>
  gamepadModal?: React.ComponentType<{ onClose: () => void }>
}

const Nothing = () => null

/**
 * Anything the shell shows as a modal is registered in the modal stack here,
 * once, for default and themed alike.
 *
 * The modals used to register themselves, which meant a theme that replaced one
 * and forgot silently broke the screens behind it: the dashboard kept receiving
 * the d-pad while the menu was open, so the cursor moved in two places at once.
 * A rule every theme must remember is a rule the host should enforce.
 */
function ModalScope({ children }: { children: React.ReactNode }) {
  const { openModal, closeModal } = useStore()
  useEffect(() => {
    openModal()
    return () => closeModal()
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  return <>{children}</>
}

export default function DefaultShell(parts: ShellParts = {}) {
  const Background = parts.background ?? Nothing
  const Decor = parts.decor ?? Nothing
  const ScreensaverC = parts.screensaver ?? Screensaver
  const TopBarC = parts.topbar ?? TopBar
  const HomeC = parts.home ?? (() => <HomeScreen onLaunchApp={launchApp} />)
  const LibraryC = parts.library ?? LibraryScreen
  const SettingsC = parts.settings ?? SettingsModal
  const PowerC = parts.powerModal ?? PowerModal
  const GamepadC = parts.gamepadModal ?? GamepadModal

  const [showSettings, setShowSettings] = useState(false)
  const [showPower, setShowPower] = useState(false)
  const [showGamepad, setShowGamepad] = useState(false)
  const { screen, sessionGameKey } = useStore()

  const gamepadOpenRef = useRef(showGamepad)
  useEffect(() => { gamepadOpenRef.current = showGamepad }, [showGamepad])
  const lastClosePress = useRef(0)

  // Which screen a button opens is the shell's business, not the kernel's —
  // a theme that lays its menus out differently binds its own.
  useEffect(() => {
    const busy = () => useStore.getState().powerPending !== null
    const offs = [
      // Toggle-close always works; opening is refused while another modal is on
      // screen, otherwise both sets of handlers fire on every press.
      onGp('gp:menu', () => {
        if (!busy()) setShowSettings(s => s ? false : useStore.getState().modalDepth === 0)
      }),
      onGp('gp:power', () => {
        if (!busy()) setShowPower(s => s ? false : useStore.getState().modalDepth === 0)
      }),
      // □ opens the controller screen on one press but closes it only on a
      // double press — every button has to stay free for testing in there.
      onGp('gp:x', () => {
        if (busy()) return
        if (!gamepadOpenRef.current) {
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
    ]
    return () => offs.forEach(off => off())
  }, [])

  return (
    <div style={{
      width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column',
      fontFamily: "'Outfit', sans-serif", color: '#fff',
      background: screen === 'home'
        ? 'radial-gradient(ellipse 70% 50% at 50% 30%, rgba(124,58,237,0.07) 0%, transparent 70%), #09090f'
        : '#09090f',
      overflow: 'hidden',
    }}>
      {/* The shell owns the stacking, so a theme never writes a z-index and can
          never paint over a screen it did not replace — which is exactly how
          the first version broke. */}
      <div style={{ position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none' }}>
        <Background />
      </div>

      <ScreensaverC />

      {/* Mounted from the first frame, behind the opaque splash: systems,
          playtime and game counts are fetched while the boot animation plays,
          so the dashboard is already populated when it fades away. */}
      <div style={{ position: 'relative', zIndex: 1, display: 'contents' }}>
        <TopBarC onSettings={() => setShowSettings(true)} onPower={() => setShowPower(true)} />
        <Toasts />

        {/* Both screens stay mounted at all times — toggled via display:none.
            This prevents the re-mount/re-fetch flash when navigating home. */}
        <div style={{ position: 'relative', zIndex: 1, flex: 1, display: screen === 'home' ? 'flex' : 'none', flexDirection: 'column', overflow: 'hidden' }}>
          <HomeC />
        </div>
        <div style={{ position: 'relative', zIndex: 1, flex: 1, display: screen === 'library' ? 'flex' : 'none', flexDirection: 'column', overflow: 'hidden' }}>
          <LibraryC />
        </div>
      </div>

      <AnimatePresence>
        {showSettings && (
          <ModalScope key="settings">
            <SettingsC onClose={() => setShowSettings(false)} />
          </ModalScope>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {showPower && (
          <ModalScope key="power">
            <PowerC onClose={() => setShowPower(false)} />
          </ModalScope>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {showGamepad && (
          <ModalScope key="gamepad">
            <GamepadC onClose={() => setShowGamepad(false)} />
          </ModalScope>
        )}
      </AnimatePresence>

      {/* Above everything, never interactive, and gone while a game runs — the
          emulator owns the screen then. */}
      {!sessionGameKey && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 400, pointerEvents: 'none' }}>
          <Decor />
        </div>
      )}
    </div>
  )
}
