import {createArtwork} from './lib/artwork.js'
import {createSession} from './lib/session.js'
import {createChrome} from './views/chrome.js'
import {createHome} from './views/home.js'
import {createLibrary} from './views/library.js'
import {createController} from './views/controller.js'
import {createSplash} from './views/splash.js'

export default function createOrbit(sdk) {
  const {html} = sdk.ui
  const artwork = createArtwork(sdk)
  const sessions = createSession(sdk, artwork)
  const {TopBar, Footer} = createChrome(sdk, sessions)
  const Home = createHome(sdk, artwork, sessions, Footer)
  const Library = createLibrary(sdk, artwork, sessions, Footer)
  const Settings = sdk.defaults.createSettings(sdk, {}, {skin: 'orbit-settings'})
  const Power = sdk.defaults.createPowerView(sdk)
  const Controller = createController(sdk)
  const Background = () => html`<div className="orbit-background"><span /><span /></div>`
  function Shell() {
    // One binding for the whole shell rather than one per screen: L2 manages
    // whatever is suspended, from anywhere, and two registrations would fire
    // twice on one press.
    sessions.useSessionShortcut()
    return html`<div className="orbit-root"><${sdk.defaults.Shell} background=${Background} topbar=${TopBar}
      homeView=${Home} libraryView=${Library} settings=${Settings} powerView=${Power} gamepadView=${Controller} />
      <${sessions.Panel} /></div>`
  }
  // `sessionBar` is optional and the host draws its own if a theme omits it —
  // see themeLoader's OPTIONAL_SURFACES. Orbit supplies the picture only.
  return {shell: Shell, splash: createSplash(sdk), sessionBar: sessions.Bar}
}
