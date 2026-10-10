import {createTabs} from './lib/tabs.js'
import {createCollection} from './lib/collection.js'
import {createArt} from './lib/art.js'
import {createIcon} from './lib/icons.js'
import {createChips} from './views/chips.js'
import {createCards} from './views/cards.js'
import {createFooter} from './views/footer.js'
import {createDetails} from './views/details.js'
import {createSearch} from './views/search/index.js'
import {createHome} from './views/home.js'
import {createLibrary} from './views/library/index.js'
import {createTopBar} from './views/topbar.js'
import {createBackground} from './views/background.js'
import {createSplash} from './views/splash.js'
import {createCeremony} from './views/ceremony.js'
import {createSession} from './views/session.js'
import {createJellySettings} from './views/settings.js'
import {createController} from './views/controller.js'
import {createStandby} from './views/standby/index.js'
import {SOUNDS} from './lib/sounds.js'
import {followProfiles} from './lib/favourites.js'

/** Every Jelly screen, built over one shared context. The theme and its tests
 * both start here, so they cannot wire it differently. */
export function createParts(sdk) {
  followProfiles(sdk)
  const tabs = createTabs(sdk)
  const collection = createCollection(sdk)
  const art = createArt(sdk)
  const Icon = createIcon(sdk)
  const cards = createCards(sdk, {art, Icon})
  const Details = createDetails(sdk, {cards, Icon})
  // Doors the shell (Settings, Power) and Home (search) own, filled in as
  // those render, for screens that need to open one.
  const actions = {settings: null, power: null, search: null, gameOptions: null, retry: () => collection.retry()}
  const ctx = {tabs, collection, art, cards, Icon, Details, actions,
    chips: createChips(sdk, {Icon}), Footer: createFooter(sdk), Search: createSearch(sdk, {cards, Details, Icon})}
  return {ctx, Home: createHome(sdk, ctx), Library: createLibrary(sdk, ctx), TopBar: createTopBar(sdk, ctx),
    Background: createBackground(sdk, {Icon}), session: createSession(sdk, {Icon})}
}

/** Jelly: the wiring and nothing else. Launching, sessions, the library's
 * loading and sort, settings, power and the controller screen stay the host's. */
export default function createJelly(sdk) {
  const {html} = sdk.ui
  const {ctx, Home, Library, TopBar, Background, session} = createParts(sdk)
  const homeGameOptions = () => ctx.actions.gameOptions?.() || null
  const Settings = createJellySettings(sdk)
  const Power = sdk.defaults.createPowerView(sdk, {skin: 'jelly-power'})
  const Controller = createController(sdk)
  // Undefined on a host before SDK 12, which then keeps its own slideshow.
  const Standby = createStandby(sdk, ctx)

  function Shell() {
    return html`<div className="jelly-app">
      <${sdk.defaults.Shell} background=${Background} topbar=${TopBar}
        homeView=${Home} libraryView=${Library} settings=${Settings}
        homeGameOptions=${homeGameOptions}
        powerView=${Power} gamepadView=${Controller} screensaver=${Standby}
        homeOmit=${['nav', 'pages', 'confirm']} libraryOmit=${['nav', 'confirm', 'sort']} />
    </div>`
  }

  return {
    splash: createSplash(sdk),
    shell: Shell,
    ceremony: createCeremony(sdk),
    sounds: SOUNDS,
    sessionBar: session.Bar,
    sessionMenu: session.Menu,
    whoIsPlaying: sdk.defaults.createWhoIsPlaying?.(sdk, {skin: 'jelly-who'}),
    rumble: {
      'gp:confirm': {duration: 30, strong: 0.25},
      'gp:back': {duration: 20, weak: 0.35},
    },
  }
}
