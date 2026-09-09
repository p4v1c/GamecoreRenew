import {createSession} from './lib/session.js'
import {createTabs} from './lib/tabs.js'
import {createTopBar} from './views/topbar.js'
import {createHome} from './views/home.js'
import {createLibrary} from './views/library.js'
import {createController} from './views/controller.js'
import {createSplash} from './views/splash.js'

/**
 * Orbit — the interactive mockup, over the real box.
 *
 * Four tabs: Games, Consoles, Library, Applications. Three of them are the
 * host's `home` screen with Orbit's own tab state on top; the fourth IS the
 * host's library screen. See lib/tabs.js for why that split is the honest one
 * rather than a workaround.
 *
 * `homeOmit` is the one thing Orbit takes back from the host. The home screen's
 * d-pad walks the SYSTEM grid, and two of Orbit's three home tabs are not a
 * system grid — a rail of recently played games, and a rail of applications. Left
 * in place, the host's cursor moved a selection nobody could see, and ✕ opened
 * whatever console it had landed on. Taking the bindings means owning what they
 * do, which views/home.js does; the cost is written down in HomeScreen beside
 * the same note for `libraryOmit`.
 *
 * The library keeps ALL of the host's behaviour — sort, search keyboard,
 * per-game options, launch, playtime — because that is the screen the contract
 * says a theme draws and does not reimplement.
 */
export default function createOrbit(sdk) {
  const {html} = sdk.ui
  const sessions = createSession(sdk)
  const tabs = createTabs(sdk)

  // Every tab needs the system list, and only `homeView` is handed it. Shared
  // through a ref rather than fetched twice: the host already has the answer.
  const systemsRef = {current: []}

  const TopBar = createTopBar(sdk, tabs, systemsRef)
  const Home = createHome(sdk, tabs, sessions, systemsRef)
  const Library = createLibrary(sdk, tabs, sessions, systemsRef)
  const Settings = sdk.defaults.createSettings(sdk, {}, {skin: 'orbit-settings'})
  const Power = sdk.defaults.createPowerView(sdk)
  const Controller = createController(sdk)

  const Background = () => html`<div className="scenery" aria-hidden="true">
    <div className="backdrop" /><div className="shade" /><div className="grain" /></div>`

  function Shell() {
    // L2 and the session menu belong to the host now — one binding for every
    // theme, and no second panel to collide with it.
    return html`<div className="orbit-app">
      <${sdk.defaults.Shell} background=${Background} topbar=${TopBar}
        homeView=${Home} libraryView=${Library} settings=${Settings}
        powerView=${Power} gamepadView=${Controller}
        homeOmit=${['nav', 'pages', 'confirm']} />
    </div>`
  }

  return {shell: Shell, splash: createSplash(sdk),
          sessionBar: sessions.Bar, sessionMenu: sessions.Menu}
}
