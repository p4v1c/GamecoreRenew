/**
 * Summer — a beach at the hour it actually is.
 *
 * Ported from the "GameCore Summer" mockup: the ocean renderer kept nearly
 * verbatim (lib/ocean.js), the screens rebuilt on the theme SDK so they use
 * real systems, playtime and pads and the host's single input bus.
 *
 *   views/  splash · background (ocean) · decor (dune) · home · library
 *           topbar · gamepad
 *   lib/    ocean (WebGL) · ambience (synthesized surf) · idle
 *
 * Settings and the power menu are the host's, dressed by the stylesheet.
 * This file only wires views together; behaviour stays with the host.
 * Contract: docs/themes/README.md
 */
import { createUseIdle } from './lib/idle.js'
import { createBackground } from './views/background.js'
import { createDecor } from './views/decor.js'
import { createTopBar } from './views/topbar.js'
import { createHomeView } from './views/home.js'
import { createLibraryView } from './views/library.js'
import { createSplash } from './views/splash.js'
import { createGamepadView } from './views/gamepad.js'
import { createSessionBar, createSessionMenu } from './views/session.js'
import { createWarp } from './views/warp.js'
import { createBox3D } from './views/box3d.js'
import { createScreensaver } from './views/screensaver.js'

export default (sdk) => {
  // The two screens this theme shares with Summer and with the built-in
  // default. They come off the sdk now rather than off a relative path:
  // they are host code, so no theme can ship a stale copy of them.
  const { createSettings, createPowerView } = sdk.defaults
  const { html } = sdk.ui
  const useIdle = createUseIdle(sdk)

  const Background = createBackground(sdk, useIdle)
  const Decor = createDecor(sdk, useIdle)
  const TopBar = createTopBar(sdk)
  const HomeView = createHomeView(sdk)
  const LibraryView = createLibraryView(sdk)
  // The same settings screen Shelf draws, off `sdk.defaults`. It
  // carries no colour — theme.css dresses its `gcs-*` classes in sea glass, and
  // the ocean stays visible behind it because the screen is a scrim rather than
  // a page of its own.
  const Settings = createSettings(sdk, {}, { TopBar })

  const Warp = createWarp(sdk)
  // The same box the detail panel draws, so a game asleep looks like the same
  // object it is awake — and its idle drift, which exists in the library to
  // hint that the box turns, is what a screensaver wanted anyway.
  const Screensaver = createScreensaver(sdk, createBox3D(sdk))

  // The host mounts the warp in its handover layer. `decor` is unmounted when
  // a session opens, which is precisely when this has to remain visible.
  const Shell = () => html`
    <div class="sm-root">
      <${sdk.defaults.Shell}
        background=${Background}
        decor=${Decor}
        topbar=${TopBar}
        homeView=${HomeView}
        libraryView=${LibraryView}
        settings=${Settings}
        screensaver=${Screensaver}
        powerView=${createPowerView(sdk)}
        gamepadView=${createGamepadView(sdk)} />
    </div>`

  // Optional surface: the host draws its own bar if a theme omits one, so the
  // way back to a suspended game cannot be lost to a theme. Summer draws it as
  // sea glass on the tideline — see views/session.js.
  return { splash: createSplash(sdk), shell: Shell,
           sessionBar: createSessionBar(sdk), sessionMenu: createSessionMenu(sdk),
           ceremony: Warp }
}
