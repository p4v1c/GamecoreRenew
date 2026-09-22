import {createFooter} from './views/footer.js'
import {createBackdrop} from './lib/backdrop.js'
import {createSession} from './lib/session.js'
import {createTabs} from './lib/tabs.js'
import {createTopBar} from './views/topbar.js'
import {createHome} from './views/home.js'
import {createLibrary} from './views/library.js'
import {createController} from './views/controller.js'
import {createSplash} from './views/splash.js'
import {createCeremony} from './views/ceremony.js'

/** Orbit's mockup over the host's real catalogue, library and session controls.
 * SDK 6 lets the grid own directional focus while the host keeps launch/search. */
export default function createOrbit(sdk) {
  const {html} = sdk.ui
  const backdrop = createBackdrop(sdk)
  const sessions = createSession(sdk)
  const tabs = createTabs(sdk)
  // After `tabs`: the footer's hints follow the tab, and a `const` read before
  // its declaration is a ReferenceError, not an undefined.
  const footer = createFooter(sdk, tabs)

  // Every tab needs the system list, and only `homeView` is handed it. Shared
  // through a ref rather than fetched twice: the host already has the answer.
  const systemsRef = {current: []}

  const TopBar = createTopBar(sdk, tabs, systemsRef)
  const Home = createHome(sdk, tabs, sessions, systemsRef, backdrop, footer)
  const Library = createLibrary(sdk, tabs, sessions, systemsRef, backdrop)
  const Background = backdrop.Background
  // Settings is a full screen of its own, PS5-style: a category list, one page
  // at a time, details in dialogs. It stands on Home's own backdrop — the same
  // component, so the same picture, shade and grain — rather than on a panel
  // floating over a blurred dashboard.
  const Settings = sdk.defaults.createSettings(sdk, {}, {
    skin: 'orbit-settings', Background, layout: 'index', detail: 'dialog',
  })
  const Power = sdk.defaults.createPowerView(sdk, {skin: 'orbit-power'})
  const Controller = createController(sdk)
  const Ceremony = createCeremony(sdk)

  function Shell() {
    // L2 and the session menu belong to the host now — one binding for every
    // theme, and no second panel to collide with it.
    //
    return html`<div className="orbit-app">
      <${sdk.defaults.Shell} background=${Background} topbar=${TopBar}
        homeView=${Home} libraryView=${Library} settings=${Settings}
        powerView=${Power} gamepadView=${Controller}
        homeOmit=${['nav', 'pages', 'confirm']} libraryOmit=${['nav', 'confirm', 'sort']} />
      <${footer.Component} />
    </div>`
  }

  return {shell: Shell, splash: createSplash(sdk),
          sessionBar: sessions.Bar, sessionMenu: sessions.Menu, ceremony: Ceremony}
}
