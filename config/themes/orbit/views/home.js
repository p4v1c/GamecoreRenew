import {createDetails} from './details.js'
import {createJacket} from '../lib/jacket.js'
import {createArt} from '../lib/art.js'
import {createHomeHooks} from './home/hooks.js'
import {createGamesTab} from './home/games.js'
import {createConsolesTab} from './home/consoles.js'
import {createApplicationsTab} from './home/applications.js'

const ICON = {
  play: '<path d="m7 4 14 8-14 8z"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  heart: '<path d="M20.8 4.9a5.5 5.5 0 0 0-7.8 0L12 6l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.3a5.5 5.5 0 0 0 0-7.8Z"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
}

export function createHome(sdk, tabs, sessions, systemsRef, backdrop, footer) {
  const {html, useEffect} = sdk.ui
  const Details = createDetails(sdk)
  const Jacket = createJacket(sdk)
  const Art = createArt(sdk)
  const svg = (name) => html`<svg viewBox="0 0 24 24" aria-hidden="true"
    dangerouslySetInnerHTML=${{__html: ICON[name]}} />`
  const hooks = createHomeHooks(sdk, tabs, systemsRef)

  const GamesTab = createGamesTab({sdk, tabs, sessions, backdrop, Details, Jacket, Art, svg, hooks})
  const ConsolesTab = createConsolesTab({sdk, tabs, backdrop, Art, svg, hooks})
  const ApplicationsTab = createApplicationsTab({sdk, tabs, sessions, backdrop, Art, svg, hooks})

  return function Home(props) {
    const tab = tabs.useTab()
    systemsRef.current = props.systems
    useEffect(() => {footer?.update(props.systems, props.totals)}, [props.systems, props.totals.games])
    const View = tab === 'systems' ? ConsolesTab : tab === 'applications' ? ApplicationsTab : GamesTab
    return html`<main className="orbit-main"><${View} ...${props} /></main>`
  }
}
