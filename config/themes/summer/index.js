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
 *   splash.js      the boot animation      home.js      the dashboard's look
 *   background.js  the ocean               settings.js  the menu
 *   decor.js       the dune                topbar.js    the status bar
 *   library.js     the game list          themes.js    the theme picker
 *   ocean.js       the renderer            idle.js      shared: asleep or busy?
 *
 * This file only wires them together. It holds no markup and no behaviour on
 * purpose: everything a screen *does* — paging, focus, the modal stack, the
 * button bindings — belongs to the host, so a themed frontend and the default
 * one behave identically and only the UI differs.
 *
 * Contract: docs/themes/README.md
 */
import { createUseIdle } from './idle.js'
import { createBackground } from './background.js'
import { createDecor } from './decor.js'
import { createTopBar } from './topbar.js'
import { createHomeView } from './home.js'
import { createLibraryView } from './library.js'
import { createSettings } from './settings.js'
import { createThemesPage } from './themes.js'
import { createSplash } from './splash.js'

export default (sdk) => {
  const { html } = sdk.ui
  const useIdle = createUseIdle(sdk)

  const Background = createBackground(sdk, useIdle)
  const Decor = createDecor(sdk, useIdle)
  const TopBar = createTopBar(sdk)
  const HomeView = createHomeView(sdk)
  const LibraryView = createLibraryView(sdk)
  const Settings = createSettings(sdk, { themes: createThemesPage(sdk) })

  const Shell = () => html`
    <${sdk.defaults.Shell}
      background=${Background}
      decor=${Decor}
      topbar=${TopBar}
      homeView=${HomeView}
      libraryView=${LibraryView}
      settings=${Settings} />`

  return { splash: createSplash(sdk), shell: Shell }
}
