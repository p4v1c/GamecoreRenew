import {createPlayTab} from './home/play.js'
import {createCollectionTab} from './home/collection.js'
import {createConsolesTab} from './home/consoles.js'

const HINTS = {
  play: [['← → ↑ ↓', 'Move'], ['✕', 'Select'], ['L1 R1', 'Tabs'], ['△', 'Search'],
    ['□', 'Controller'], ['Options', 'Settings']],
  collection: [['← → ↑ ↓', 'Move'], ['✕', 'Details'], ['○', 'Play'], ['L1 R1', 'Tabs'],
    ['△', 'Search'], ['Options', 'Settings']],
  consoles: [['← → ↑ ↓', 'Move'], ['✕', 'Open'], ['○', 'Play'], ['L1 R1', 'Tabs'],
    ['△', 'Search'], ['Options', 'Settings']],
}

/** The dashboard: Play, Collection and Consoles over the host's home screen.
 *
 * The host's d-pad, L1/R1 and ✕ are omitted for this screen (index.js), so
 * each tab binds its own through `useSpatial`. The details panel and the search are
 * drawn here, inside the screen, so the shell's stacking covers them. */
export function createHome(sdk, ctx) {
  const {html, useState, useEffect} = sdk.ui
  const {tabs, collection, actions, Details, Search} = ctx
  const tabsView = {
    play: createPlayTab(sdk, {...ctx, hints: HINTS.play}),
    collection: createCollectionTab(sdk, {...ctx, hints: HINTS.collection}),
    consoles: createConsolesTab(sdk, {...ctx, hints: HINTS.consoles}),
  }

  return function Home(props) {
    const tab = tabs.useTab()
    const data = collection.useCollection(props.systems)
    const [details, setDetails] = useState(null)
    const [search, setSearch] = useState(false)

    const openSearch = () => { if (!sdk.nav.get().modalDepth) setSearch(true) }
    useEffect(() => {
      actions.search = () => {
        if (sdk.nav.get().screen === 'library') sdk.nav.goHome()
        openSearch()
      }
      actions.retry = collection.retry
      actions.systems = props.systems
    })

    const View = tabsView[tab] || tabsView.play
    return html`<main className="jl-main" data-tab=${tab}>
      <${View} key=${tab} data=${data} systems=${props.systems} counts=${props.counts}
        actions=${actions} onDetails=${setDetails} onSearch=${openSearch} />
      ${search ? html`<${Search} data=${data} systems=${props.systems}
        onClose=${() => setSearch(false)} />` : null}
      ${details ? html`<${Details} game=${details} onClose=${() => setDetails(null)} />` : null}
    </main>`
  }
}
