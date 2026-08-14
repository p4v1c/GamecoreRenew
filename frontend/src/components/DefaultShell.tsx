import { useState, useEffect, useRef } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useStore } from '../store'
import { onGp } from '../hooks/useGamepad'

import TopBar from './TopBar'
import HomeScreen from './HomeScreen'
import LibraryScreen from './LibraryScreen'
import SettingsScreen from './modals/SettingsScreen'
import PowerModal from './modals/PowerModal'
import GamepadModal from './modals/GamepadModal'
import Screensaver from './Screensaver'
import Toasts from './ui/Toasts'
import { launchApp } from './defaults'
import type { HomeViewProps } from './HomeScreen/types'
import type { LibraryViewProps } from './LibraryScreen/types'
import type { PowerViewProps } from './modals/power/types'
import type { GamepadViewProps } from './modals/gamepad/types'
import type { ToastsViewProps } from './ui/toasts/types'

/**
 * The default frontend, as one component.
 *
 * A theme replaces this whole thing — that is the model: picking a theme swaps
 * the frontend, and anything it does not provide (the splash, the rescue combo,
 * the input bus) stays with the kernel in App.tsx.
 *
 * A theme supplies the parts below and nothing else. They are views: what the
 * screens look like. What they *do* — paging, focus, the modal stack, the
 * button bindings — stays here, so a themed frontend and the default one behave
 * identically and only the UI differs.
 */

/** The controller screen only exits on a second □ within this window. */
const CONTROLLER_CLOSE_MS = 1000

export interface ShellParts {
  background?: React.ComponentType
  decor?: React.ComponentType
  screensaver?: React.ComponentType
  topbar?: React.ComponentType<{ onSettings: () => void; onPower: () => void }>
  /**
   * The dashboard's *markup* — not the dashboard. Paging, focus and launching
   * stay in HomeScreen so a themed grid and the default one behave identically;
   * a theme that got to reimplement them always got them subtly wrong.
   */
  homeView?: React.ComponentType<HomeViewProps>
  /** The library's markup. Sorting, search and launching stay with the host. */
  libraryView?: React.ComponentType<LibraryViewProps>
  /**
   * Library shortcuts this theme binds itself, so the host lets go of them.
   *
   * The same idea as `powerOmit`, for the same reason: the host cannot know
   * which buttons a theme has advertised on its own screen, and two handlers
   * on one button is never what either of them meant.
   *
   * It exists because of exactly that. The host opens the per-game options on
   * R2 — "because every face button is already spoken for on this screen" —
   * and Shelf's library binds R2 to cycle how the shelf is stacked, and prints
   * `R2  <mode>` in its own hint bar. Pressing it did both: the box turned AND
   * a menu nobody asked for appeared over it, and pressing again turned the box
   * behind the menu. Only `'options'` is recognised today.
   *
   * A theme that takes a shortcut takes responsibility for offering the thing
   * some other way. Nothing here enforces that, because there is no honest way
   * to check it — but see LibraryScreen, which says what is lost.
   */
  libraryOmit?: string[]
  settings?: React.ComponentType<{ onClose: () => void }>
  /**
   * Markup for the power menu and the controller screen. Their flows stay with
   * the host — the two-press shutdown confirmation and its failsafe, and the
   * live pad diagram — because those are the two places where a theme getting
   * it wrong costs more than a misaligned pixel.
   */
  powerView?: React.ComponentType<PowerViewProps>
  /**
   * Power-menu ids this theme offers somewhere else, so they leave that menu.
   *
   * Only the mapping utilities can go; PowerModal refuses to drop restart,
   * shutdown or desktop whatever is passed. A theme that moves "Scan mapping"
   * into its own Controllers screen says so here and stops showing it twice.
   */
  powerOmit?: string[]
  gamepadView?: React.ComponentType<GamepadViewProps>
  /**
   * The notification stack's markup. The queue, the durations and the handover
   * to the native HUD stay with the host.
   *
   * It is a part because it was not one: `Toasts` was rendered here
   * unconditionally, so a theme that wrote its own shell kept the default's
   * toasts in the default's corner in the default's colours — and one that
   * rendered its own tree instead of `Shell` lost every notification there is.
   * A ROM finishing its upload, a pad going flat and the offer to map an
   * unrecognised controller are not decoration.
   */
  toasts?: React.ComponentType<ToastsViewProps>
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

  // The stacking is registered here too, for the same reason and once.
  //
  // The screens sit at z-index 1 so they clear the background, which puts a
  // modal at `auto` UNDERNEATH them. The default modals get away with it
  // because ui/Overlay sets z-index 500 on itself — but a theme writes its own
  // modal markup and does not use Overlay, and docs/themes/README promises it
  // "never writes a z-index". That held everywhere except the one place it
  // mattered: a themed settings panel opened *behind* the dashboard, tiles
  // painting straight over it.
  //
  // Not `position: fixed; inset: 0` here: the children already cover the
  // viewport when they want to, and a full-screen wrapper would swallow clicks
  // meant for a panel that does not. Relative + z-index is the whole job — it
  // creates the stacking context and takes no space.
  return <div style={{ position: 'relative', zIndex: 500 }}>{children}</div>
}

/**
 * What the built-in power menu leaves out, when a theme has not said.
 *
 * Saving a pad's controls is not a way to end a session. The two mapping rows
 * were in this menu for one reason — it had the two-press confirmation and no
 * settings screen did — and both shipped themes moved them to
 * Settings → Controllers and declared `powerOmit` to drop them here.
 *
 * The built-in UI could not follow, because its settings screen was a list of
 * ten host pages and Controllers was not one of them. It draws the same rail
 * the themes draw now, Controllers included, so the reason is gone and the
 * menu is the three ways a session ends.
 *
 * `??`, not `||`: a theme that deliberately passes `[]` wants the full menu,
 * and an empty array is not an absent one.
 */
export const POWER_OMIT = ['scan', 'forget']

export default function DefaultShell(parts: ShellParts = {}) {
  const Background = parts.background ?? Nothing
  const Decor = parts.decor ?? Nothing
  const ScreensaverC = parts.screensaver ?? Screensaver
  const TopBarC = parts.topbar ?? TopBar
  // The rail screen, the same one Shelf and Summer draw — see
  // modals/SettingsScreen.tsx. `SettingsModal`, the centred list this used
  // to be, is still exported for a theme that prefers it.
  const SettingsC = parts.settings ?? SettingsScreen

  const [showSettings, setShowSettings] = useState(false)
  const [showPower, setShowPower] = useState(false)
  const [showGamepad, setShowGamepad] = useState(false)
  const [startInWizard, setStartInWizard] = useState(false)
  /**
   * One subscription per value, not one to the whole store.
   *
   * Both screens stay mounted for the session — the shell hides one with
   * `display: none` so that going home does not re-fetch — which means anything
   * that re-renders this component re-renders BOTH of them, plus the wall and
   * the bar. `useStore()` with no selector subscribes to every field, so moving
   * the cursor one game along the shelf re-rendered the whole dashboard behind
   * it, invisibly, once per press. See shellRerender.test.tsx.
   */
  const screen = useStore(s => s.screen)
  const sessionGameKey = useStore(s => s.sessionGameKey)
  const remapRequest = useStore(s => s.remapRequest)

  // The unrecognised-controller toast asks for the wizard; the shell is what
  // can grant it, because it owns which modal is up. Straight into the wizard
  // rather than onto the controller screen: the player is holding a pad that
  // does not work, and one more screen to cross is one more screen to cross
  // with a controller that cannot cross it.
  useEffect(() => {
    if (remapRequest === 0) return
    setStartInWizard(true)
    setShowGamepad(true)
  }, [remapRequest])

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
        <Toasts view={parts.toasts} />

        {/* Both screens stay mounted at all times — toggled via display:none.
            This prevents the re-mount/re-fetch flash when navigating home. */}
        <div style={{ position: 'relative', zIndex: 1, flex: 1, display: screen === 'home' ? 'flex' : 'none', flexDirection: 'column', overflow: 'hidden' }}>
          <HomeScreen onLaunchApp={launchApp} view={parts.homeView} />
        </div>
        <div style={{ position: 'relative', zIndex: 1, flex: 1, display: screen === 'library' ? 'flex' : 'none', flexDirection: 'column', overflow: 'hidden' }}>
          <LibraryScreen view={parts.libraryView} omit={parts.libraryOmit} />
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
            <PowerModal onClose={() => setShowPower(false)} view={parts.powerView} omit={parts.powerOmit ?? POWER_OMIT} />
          </ModalScope>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {showGamepad && (
          <ModalScope key="gamepad">
            <GamepadModal
              onClose={() => { setShowGamepad(false); setStartInWizard(false) }}
              startInWizard={startInWizard}
              view={parts.gamepadView}
            />
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
