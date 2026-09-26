/**
 * Shelf — your library as boxed games on a papered wall.
 *
 * Spines on a shelf; the selected game turned towards you as a solid built from
 * `box-front`, `box-spine`, `box-back` (already warmed by the backend). L2 turns
 * it over, R2 restacks, ✕ slots the cartridge in.
 *
 *   views/  splash · background (the wall) · box (solid, spines) · topbar
 *           home (consoles) · library (the shelf) · cartridge · gamepad
 *   lib/    accent · names · dossier · browse (flip, restack) · idle
 *
 * Settings and the power menu are the host's (`sdk.defaults.createSettings`,
 * `createPowerView`), dressed via `gcs-*` classes. The wallpaper is
 * `--gc-paper-pattern` in the stylesheet, shared with Settings.
 * No behaviour here: paging, focus, sorting, launching stay with the host.
 * Contract: docs/themes/README.md
 */
import { createAccentStore } from './lib/accent.js'
import { createUseIdle } from './lib/idle.js'
import { createUseBrowse } from './lib/browse.js'
import { createUseDossier } from './lib/dossier.js'

import { createBackground } from './views/background.js'
import { createTopBar } from './views/topbar.js'
import { createHomeView } from './views/home.js'
import { createLibraryView } from './views/library.js'
import { createBox } from './views/box.js'
import { createCartridge } from './views/cartridge.js'
import { createSplash } from './views/splash.js'
import { createGamepadView } from './views/gamepad.js'
import { createSessionBar, createSessionMenu } from './views/session.js'
import { createCeremony } from './views/ceremony.js'

/**
 * R2 turns the box on this shelf — `lib/browse.js` binds it and the library's
 * own hint bar prints `R2  <mode>`. The host binds the same button to the
 * per-game overlay picker, so one press did both: the box turned AND a menu
 * nobody asked for opened over it, and the next press turned the box behind
 * that menu.
 *
 * Declaring it here is what makes the host let go. The cost is stated in
 * LibraryScreen: this theme then has no route to that picker.
 */
const LIBRARY_OMIT = ['options']

export default (sdk) => {
  // The two screens this theme shares with Summer and with the built-in
  // default. They come off the sdk now rather than off a relative path:
  // they are host code, so no theme can ship a stale copy of them.
  const { createSettings, createPowerView } = sdk.defaults
  const { html } = sdk.ui

  // One accent, two trees. The wall lives in `background` and the thing that
  // decides its colour lives in `libraryView`; they never meet, so the value
  // travels through a subscription rather than through the document.
  const accent = createAccentStore(sdk)
  const useIdle = createUseIdle(sdk)

  const Background = createBackground(sdk, accent, useIdle)
  const TopBar = createTopBar(sdk)
  const HomeView = createHomeView(sdk, accent)
  const LibraryView = createLibraryView(sdk, {
    accent,
    useBrowse: createUseBrowse(sdk),
    useDossier: createUseDossier(sdk),
    Box: createBox(sdk),
    Cartridge: createCartridge(sdk),
  })
  // Every settings category is now an inline page inside the settings screen
  // (views/pages/), so there is nothing left to override as a full-screen
  // overlay — the two files that used to do that were superseded rather than
  // kept as dead routes. `ownPages` stays in the signature because it is the
  // seam a fork uses to replace one page without editing views/settings.js.
  const Settings = createSettings(sdk, {}, { TopBar })

  const Ceremony = createCeremony(sdk)

  const Shell = () => html`
    <${sdk.defaults.Shell}
      background=${Background}
      topbar=${TopBar}
      homeView=${HomeView}
      libraryView=${LibraryView}
      settings=${Settings}
      powerView=${createPowerView(sdk)}
      libraryOmit=${LIBRARY_OMIT}
      gamepadView=${createGamepadView(sdk)} />`

  // `sessionBar` is optional: the host draws its own if a theme omits one, so
  // the way back to a suspended game can never be lost to a theme. Shelf draws
  // it as the ledge under the shelf — see views/session.js.
  return { splash: createSplash(sdk), shell: Shell,
           sessionBar: createSessionBar(sdk), sessionMenu: createSessionMenu(sdk),
           ceremony: Ceremony }
}
