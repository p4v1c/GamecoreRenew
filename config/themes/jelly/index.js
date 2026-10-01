import {createTabs} from './lib/tabs.js'
import {createCollection} from './lib/collection.js'
import {createArt} from './lib/art.js'
import {createCards} from './views/cards.js'
import {createFooter} from './views/footer.js'
import {createDetails} from './views/details.js'
import {createSearch} from './views/search.js'
import {createHome} from './views/home.js'
import {createLibrary} from './views/library.js'
import {createTopBar} from './views/topbar.js'
import {createBackground} from './views/background.js'
import {createSplash} from './views/splash.js'
import {createCeremony} from './views/ceremony.js'
import {createSession} from './views/session.js'
import {createJellySettings} from './views/settings.js'
import {createController} from './views/controller.js'

/** Jelly: the host's real collection, consoles and settings, in jelly.
 *
 * The wiring and nothing else. Behaviour that is the host's stays the host's:
 * launching, sessions, the library's loading and sort, the settings pages, the
 * power menu's confirmation and the controller screen.
 */
export default function createJelly(sdk) {
  const {html} = sdk.ui
  const tabs = createTabs(sdk)
  const collection = createCollection(sdk)
  const art = createArt(sdk)
  const cards = createCards(sdk, art)
  const Footer = createFooter(sdk)
  const Details = createDetails(sdk, cards)
  // Doors the shell owns (Settings, Power) and Home owns (search), handed to
  // whichever screen needs one. Filled in as those components render.
  const actions = {settings: null, power: null, search: null, retry: () => collection.retry()}
  const Search = createSearch(sdk, {cards, Details})
  const ctx = {tabs, collection, art, cards, Footer, Details, Search, actions}

  const Home = createHome(sdk, ctx)
  const Library = createLibrary(sdk, ctx)
  const TopBar = createTopBar(sdk, ctx)
  const Background = createBackground(sdk)
  const Settings = createJellySettings(sdk)
  const Power = sdk.defaults.createPowerView(sdk, {skin: 'jelly-power'})
  const Controller = createController(sdk)
  const session = createSession(sdk)

  function Shell() {
    return html`<div className="jelly-app">
      <${sdk.defaults.Shell} background=${Background} topbar=${TopBar}
        homeView=${Home} libraryView=${Library} settings=${Settings}
        powerView=${Power} gamepadView=${Controller}
        homeOmit=${['nav', 'pages', 'confirm']} libraryOmit=${['nav', 'confirm', 'sort']} />
    </div>`
  }

  return {
    splash: createSplash(sdk),
    shell: Shell,
    ceremony: createCeremony(sdk),
    sessionBar: session.Bar,
    sessionMenu: session.Menu,
    rumble: {
      'gp:confirm': {duration: 30, strong: 0.25},
      'gp:back': {duration: 20, weak: 0.35},
    },
  }
}
