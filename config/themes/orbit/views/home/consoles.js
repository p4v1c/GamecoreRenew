import {
  isApp, systemName, systemMark, systemMaker, systemYear, systemStory, accent, consoleArt,
} from '../../lib/catalog.js'
import {reveal} from '../../lib/dom.js'

export function createConsolesTab({sdk, tabs, backdrop, Art, svg, hooks}) {
  const {html, useState, useEffect, useRef, useMemo} = sdk.ui
  const {useHomeKeys} = hooks

  // ── the Consoles tab ──────────────────────────────────────────────────────

  function ConsolesTab({systems, counts}) {
    const machines = useMemo(() => systems.filter((s) => !isApp(s)), [systems])
    const [idx, setIdx] = useState(() => Math.max(0, machines.findIndex(m => m.id === tabs.lastSystem())))
    const grid = useRef(null)
    const at = Math.min(idx, Math.max(0, machines.length - 1))
    const s = machines[at]

    useEffect(() => { if (s) tabs.rememberSystem(s.id) }, [s?.id])

    useEffect(() => {
      reveal(grid.current?.querySelector('[data-active="true"]'),
             {block: 'nearest', inline: 'center', behavior: 'smooth'})
    }, [at])

    const move = (d) => setIdx((i) => (i + d + machines.length) % Math.max(1, machines.length))
    const open = () => {
      if (!s) return
      tabs.rememberSystem(s.id)
      sdk.nav.goLibrary(s.id)
    }
    useHomeKeys(move, open, 'systems')
    const screen = sdk.nav.use(s => s.screen)
    useEffect(() => {if (screen === 'home' && tabs.get() === 'systems') backdrop?.select({kind: 'systems', accent: accent(sdk, s)})}, [s?.id, screen])

    if (!machines.length) {
      return html`<section id="systems-view" className="collection-view consoles-view">
        <div className="page-heading"><div><p className="eyebrow">YOUR CONSOLE COLLECTION</p>
          <h1>No consoles yet.<br /><span>Add one to begin.</span></h1></div></div>
        <p className="mock-footnote">Settings → Catalog installs an emulator.</p></section>`
    }
    return html`<section id="systems-view" className="collection-view consoles-view"
                         aria-labelledby="systems-title">
      <div className="page-heading">
        <div><p className="eyebrow">YOUR CONSOLE COLLECTION</p>
          <h1 id="systems-title">Every generation.<br /><span>One place.</span></h1></div>
        <div className="console-summary"><strong>${machines.length}</strong>
          <span>console${machines.length === 1 ? '' : 's'} & handhelds</span></div>
      </div>
      <div className="console-showcase" style=${{'--console-accent': accent(sdk, s)}}>
        <div className="console-story">
          <div className="console-kicker"><span className="console-maker">${(systemMaker(s) || 'GAMECORE').toUpperCase()}</span>
            <span>${systemYear(s)}</span><span className="dot" /><span>CONSOLE</span></div>
          <h2>${systemName(s)}</h2>
          <p>${systemStory(s)}</p>
          <div className="console-facts"><span>${counts[s.id] ?? 0} game${(counts[s.id] ?? 0) === 1 ? '' : 's'}</span>
            <span className="dot" /><span>${s.label || s.id}</span></div>
          <button className="primary-button" onClick=${open}>${svg('grid')}Browse games<span>✕</span></button>
        </div>
        <div className="console-exhibit"><span className="console-halo" /><span className="console-plinth" />
          <${Art} className="console-photo" src=${consoleArt(sdk, s)} alt=${systemName(s)} />
          <span className="exhibit-number">${String(at + 1).padStart(2, '0')}<small> / ${machines.length}</small></span>
        </div>
      </div>
      <div className="section-heading machines-heading"><h2>Choose a console</h2><span>← → to browse</span></div>
      <div className="systems-grid" ref=${grid}>
        ${machines.map((m, i) => html`<button key=${m.id}
          className=${`machine-tile ${i === at ? 'selected' : ''}`}
          data-active=${i === at ? 'true' : 'false'} aria-pressed=${String(i === at)}
          aria-label=${`View ${systemName(m)}`}
          onClick=${() => (i === at ? open() : setIdx(i))}>
          <span className="machine-image"><${Art} src=${consoleArt(sdk, m)} alt="" /></span>
          <span>${systemMark(m)}</span><small>${systemMaker(m) || (m.label || m.id)}</small>
        </button>`)}
      </div>
    </section>`
  }

  return ConsolesTab
}
