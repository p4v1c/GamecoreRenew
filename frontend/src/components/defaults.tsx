/**
 * The default UI, re-exposed as prop-less surfaces.
 *
 * Theme surfaces take no props by contract — everything comes from the SDK —
 * but the components written before themes existed take handlers. These
 * wrappers close that gap, and they are what `sdk.defaults` hands to a theme
 * that wants to wrap the default look instead of replacing it.
 */
import { playSound } from '../lib/sounds'
import { api } from '../api'
import { useStore } from '../store'

import HomeScreen from './HomeScreen'
import LibraryScreen from './LibraryScreen'
import TopBar from './TopBar'
import Screensaver from './Screensaver'
import PowerModal from './modals/PowerModal'
import GamepadModal from './modals/GamepadModal'
import { VirtualKeyboard } from './ui/VirtualKeyboard'
import SettingsModal from './modals/SettingsModal'
import { WifiPage } from './modals/settings/WifiPage'
import { AudioPage } from './modals/settings/AudioPage'
import { BluetoothPage } from './modals/settings/BluetoothPage'
import { StandbyPage } from './modals/settings/StandbyPage'
import { UpdatePage } from './modals/settings/UpdatePage'
import { DesktopPage } from './modals/settings/DesktopPage'
import { ThemesPage } from './modals/settings/ThemesPage'

/** Launching lives here rather than in App so a prop-less surface can do it. */
export async function launchApp(system: { id: string }): Promise<void> {
  playSound('launch')
  try {
    await api.games.launch(system.id)
    useStore.getState().setSession(system.id, system.id)
  } catch (e) {
    console.error('Failed to launch app:', e)
  }
}

export const DefaultHome = () => <HomeScreen onLaunchApp={launchApp} />
export const DefaultLibrary = () => <LibraryScreen />
export const DefaultScreensaver = () => <Screensaver />

/** The modals close themselves through the store-independent callbacks App owns. */
export type CloseProps = { onClose: () => void }
export const DefaultPowerModal = ({ onClose }: CloseProps) => <PowerModal onClose={onClose} />
export const DefaultGamepadModal = ({ onClose }: CloseProps) => <GamepadModal onClose={onClose} />

export type TopBarProps = { onSettings: () => void; onPower: () => void }
export const DefaultTopBar = ({ onSettings, onPower }: TopBarProps) => (
  <TopBar onSettings={onSettings} onPower={onPower} />
)

export const DefaultKeyboard = VirtualKeyboard

export const DefaultSettings = ({ onClose }: CloseProps) => <SettingsModal onClose={onClose} />

/**
 * The settings sub-pages, so a theme can restyle the menu around them without
 * reimplementing Wi-Fi scanning or the update stream. Each takes
 * { onClose, onBack } and brings its own gamepad bindings.
 */
export const DefaultSettingsPages = {
  wifi: WifiPage,
  audio: AudioPage,
  bluetooth: BluetoothPage,
  standby: StandbyPage,
  themes: ThemesPage,
  update: UpdatePage,
  desktop: DesktopPage,
}

/** Nothing behind and nothing on top, unless a theme says otherwise. */
export const DefaultBackground = () => null
export const DefaultDecor = () => null
