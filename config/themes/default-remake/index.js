/**
 * Default (remake) — the stock GameCore UI, written as an ordinary theme.
 *
 * This theme exists to be a test, not to be pretty. The question it answers is
 * the only one that tells you whether a theme SDK is finished:
 *
 *     can the default frontend be expressed through it?
 *
 * Anything the default UI can do that a theme cannot is a hole, and the only
 * reliable way to find those holes is to stand where a theme author stands and
 * try to build the thing you already have. Four were found writing this and are
 * now part of the SDK — see README.md in this folder.
 *
 * It stays in the tree afterwards as a regression test: the day someone adds a
 * capability to the default UI and forgets to expose it, this theme is what
 * stops looking like the default.
 *
 * One feature per file, like the default frontend and like `summer`:
 *
 *   views/  splash.js   the boot animation   home.js      the dashboard
 *           topbar.js   clock, IP, storage   library.js   the game list
 *           settings.js the menu             power.js     restart / shutdown
 *           gamepad.js  the live pad         screensaver.js  standby
 *           toasts.js   the notifications
 *
 *   lib/    card.js     one system tile
 *
 * This file wires them and holds no markup and no behaviour, which is the same
 * discipline the host keeps: everything a screen *does* — paging, focus, the
 * modal stack, the bindings — belongs to the host, so this theme and the
 * default behave identically and only the drawing differs.
 *
 * Contract: docs/themes/README.md
 */
import { createSplash } from './views/splash.js'
import { createTopBar } from './views/topbar.js'
import { createHomeView } from './views/home.js'
import { createLibraryView } from './views/library.js'
import { createSettings } from './views/settings.js'
import { createPowerView } from './views/power.js'
import { createGamepadView } from './views/gamepad.js'
import { createScreensaver } from './views/screensaver.js'
import { createToasts } from './views/toasts.js'

export default (sdk) => {
  const { html } = sdk.ui

  const Shell = () => html`
    <${sdk.defaults.Shell}
      topbar=${createTopBar(sdk)}
      homeView=${createHomeView(sdk)}
      libraryView=${createLibraryView(sdk)}
      settings=${createSettings(sdk)}
      powerView=${createPowerView(sdk)}
      gamepadView=${createGamepadView(sdk)}
      screensaver=${createScreensaver(sdk)}
      toasts=${createToasts(sdk)} />`

  // No `sounds` and no `rumble` on purpose. The default UI uses the host's five
  // synthesized sounds and vibrates nothing, so a faithful remake declares
  // neither — which also means this theme exercises the fallback end of both
  // cascades every time it runs.
  return { splash: createSplash(sdk), shell: Shell }
}
