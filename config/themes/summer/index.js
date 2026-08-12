/**
 * Summer — a beach at the hour it actually is.
 *
 * Ported from the "GameCore Summer" design mockup. The mockup was one 700-line
 * vanilla component that owned everything, including its own gamepad polling
 * and fake data; here the ocean renderer is kept nearly verbatim (ocean.js) and
 * the screens are rebuilt on the theme SDK, so they run on the box's real
 * systems, playtime and controllers, and share the host's single input bus.
 *
 * One feature per file, like the default frontend — the directory listing is
 * the check-list of what a theme has to dress:
 *
 *   views/  splash.js  the boot animation   home.js      the dashboard
 *           background.js  the ocean        library.js   the game list
 *           decor.js   the dune             topbar.js    the status bar
 *           gamepad.js the live pad
 *
 * The settings screen and the power menu are not here: they are shared with
 * Shelf — host code now, reached through `sdk.defaults` — and dressed by
 * theme.css.
 *
 *   lib/    ocean.js   the WebGL renderer   idle.js      asleep or busy?
 *           ambience.js  the surf, synthesized
 *
 * Split the way the frontend splits: what a screen looks like, and what it
 * needs to look like that. There is no components/HomeScreen/ here because a
 * theme supplies only the *view* of a screen — the folder would hold one file.
 *
 * This file only wires them together. It holds no markup and no behaviour on
 * purpose: everything a screen *does* — paging, focus, the modal stack, the
 * button bindings — belongs to the host, so a themed frontend and the default
 * one behave identically and only the UI differs.
 *
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

  // The launch veil is a sibling of the shell, not one of its parts. `decor` —
  // the slot for painting over everything — is unmounted by the shell the
  // moment a session opens, which is precisely when this has to start. See
  // views/warp.js. The wrapper is `display: contents`, so it adds a name to
  // the tree and nothing to the layout.
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
        powerOmit=${['scan', 'forget']}
        gamepadView=${createGamepadView(sdk)} />
      <${Warp} />
    </div>`

  return { splash: createSplash(sdk), shell: Shell }
}
