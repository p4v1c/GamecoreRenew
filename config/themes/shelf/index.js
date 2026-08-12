/**
 * Shelf — your library as objects on a papered wall.
 *
 * A system's games stand as spines; the selected one is turned towards you as
 * a real solid, assembled from the three faces the backend already warmed
 * (`box-front`, `box-spine`, `box-back` — its own `WARM_MEDIA` comment calls
 * them "the three faces the 3D box is built from"). L2 turns it over. R2
 * restacks the shelf. ✕ slots the cartridge in and the iris closes on it.
 *
 * One feature per file, the way the frontend splits — what a screen looks
 * like, and what it needs to look like that:
 *
 *   views/  splash.js     the cartridge going in     home.js      the consoles
 *           background.js the wall                   library.js   the shelf
 *           box.js        the solid and its spines   cartridge.js the media
 *           topbar.js     the shelf label            gamepad.js   the live pad
 *
 * The settings screen and the power menu are NOT here. They are the host's,
 * reached through `sdk.defaults.createSettings` and `sdk.defaults.createPowerView`
 * — the same seam as `sdk.defaults.DefaultKeyboard`. Three surfaces draw them
 * (this theme, Summer, and the built-in default), and code in the bundle is the
 * only copy no theme can ship a stale version of. They carry no colour: this
 * theme dresses them through the `gcs-*` classes in theme.css.
 *
 *   lib/    accent.js     the colour                 names.js     titles, letters
 *           dossier.js    one lookup                 regions
 *           browse.js     flip and restack           idle.js      is anyone here
 *
 * The wallpaper is not here any more: it is `--gc-paper-pattern` in theme.css,
 * one definition the wall and the settings screen both paint. paper.js
 * generated a Truchet weave for the wall alone, and two patterns that were
 * meant to be one wall is exactly how they came to differ.
 *
 * This file holds no markup and no behaviour on purpose. Everything a screen
 * *does* — paging, focus, sorting, searching, launching, the modal stack, the
 * button bindings — belongs to the host, so a shelf and the default frontend
 * behave identically and only the picture differs.
 *
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

  const Shell = () => html`
    <${sdk.defaults.Shell}
      background=${Background}
      topbar=${TopBar}
      homeView=${HomeView}
      libraryView=${LibraryView}
      settings=${Settings}
      powerView=${createPowerView(sdk)}
      powerOmit=${['scan', 'forget']}
      gamepadView=${createGamepadView(sdk)} />`

  return { splash: createSplash(sdk), shell: Shell }
}
