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
 *           topbar.js     the shelf label            settings.js  the rail
 *           themes.js     the picker                 power.js     restart/off
 *           gamepad.js    the live pad               controllers.js what is
 *                                                                  plugged in
 *
 *   lib/    paper.js      the wallpaper, as a mask   accent.js    the colour
 *           names.js      titles, letters, regions   dossier.js   one lookup
 *           browse.js     flip and restack           idle.js      is anyone here
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
import { createSettings } from './views/settings.js'
import { createThemesPage } from './views/themes.js'
import { createControllersPage } from './views/controllers.js'
import { createPowerView } from './views/power.js'
import { createGamepadView } from './views/gamepad.js'

export default (sdk) => {
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
  // `themes` overrides a host page; `controllers` adds one the host does not
  // have. Both ride the same merge — `{ ...DefaultSettingsPages, ...ownPages }`
  // — and only `themes` belongs in theme.json's settings.pages, which lists
  // host pages reached and nothing else.
  const Settings = createSettings(sdk, {
    themes: createThemesPage(sdk),
    controllers: createControllersPage(sdk),
  })

  const Shell = () => html`
    <${sdk.defaults.Shell}
      background=${Background}
      topbar=${TopBar}
      homeView=${HomeView}
      libraryView=${LibraryView}
      settings=${Settings}
      powerView=${createPowerView(sdk)}
      gamepadView=${createGamepadView(sdk)} />`

  return { splash: createSplash(sdk), shell: Shell }
}
