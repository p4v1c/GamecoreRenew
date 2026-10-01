import {
  isApp, systemName, systemMark, systemMaker, systemYear, coverColor, consoleArt, packLogo,
  appStyle, plural,
} from '../../lib/catalog.js'
import {createSpatial} from '../../lib/spatial.js'
import {homeOwnsPad} from '../../lib/presses.js'

/** Consoles: a photo card per installed console, then the applications.
 * ✕ opens a console's library (the host's screen), or launches an app,
 * resuming it when it is already in the background. */
export function createConsolesTab(sdk, {tabs, art, Icon, Footer, hints}) {
  const {html, useState, useRef, useMemo} = sdk.ui
  const {Fragment} = sdk.ui.React
  const useSpatial = createSpatial(sdk)
  const {Picture} = art

  function ConsoleCard({system, count}) {
    const maker = [systemMaker(system), systemYear(system)].filter(Boolean).join(' ')
    return html`<button type="button" className="jl-console" data-nav=${`c-${system.id}`}
        style=${{'--cover': coverColor(sdk, system)}} aria-label=${`${systemName(system)}, ${plural(count, 'jeu', 'jeux')}`}
        onClick=${() => sdk.nav.goLibrary(system.id)}>
      <span className="jl-console-stage">
        <span className="jl-console-tag">${systemMark(system)}</span>
        <span className="jl-console-ghost" aria-hidden="true">${systemMark(system)}</span>
        <${Picture} className="jl-console-photo" src=${consoleArt(sdk, system)} mark=${systemMark(system)} />
      </span>
      <span className="jl-console-caption"><b>${systemName(system)}</b>
        <small>${plural(count, 'jeu', 'jeux')}${maker ? `, ${maker}` : ''}</small>
        <span className="jl-arrow"><${Icon} name="out" /></span></span>
    </button>`
  }

  function AppCard({app, held, onOpen}) {
    const st = appStyle(app)
    return html`<button type="button" className="jl-app" data-nav=${`a-${app.id}`}
        style=${{'--cover': st.color}} aria-label=${`Ouvrir ${systemName(app)}`} onClick=${onOpen}>
      <span className="jl-app-logo"><${Picture} src=${packLogo(app)} mark=${systemMark(app)} /></span>
      <span className="jl-app-text"><b>${systemName(app)}</b><small>${st.category}</small></span>
      ${held ? html`<span className="jl-badge">En pause</span>` : null}
    </button>`
  }

  return function ConsolesTab({systems, counts, onSearch}) {
    const root = useRef(null)
    const [error, setError] = useState('')
    const {background} = sdk.session.use()
    const machines = useMemo(() => systems.filter((s) => !isApp(s)), [systems])
    const apps = useMemo(() => systems.filter(isApp), [systems])
    const heldApp = (app) => background.find((s) => s.systemId === app.id && s.gameKey === app.id)
    const openApp = (app) => {
      setError('')
      const held = heldApp(app)
      Promise.resolve(held ? sdk.session.resume(held.session) : sdk.defaults.launchApp(app))
        .catch((e) => setError(e?.message || `${systemName(app)} ne s’est pas ouvert. Réessaie.`))
    }
    useSpatial(root, {
      allowed: () => homeOwnsPad(sdk) && tabs.get() === 'consoles',
      initial: '.jl-consoles [data-nav]',
      keys: {l1: () => tabs.step(-1), r1: () => tabs.step(1), y: onSearch, back: () => tabs.go('play')},
    }, [systems.length])

    return html`<section className="jl-page jl-consoles-page" ref=${root} aria-labelledby="jl-sys-title">
      <div className="jl-head">
        <div><span className="jl-eyebrow">Les consoles</span><h1 id="jl-sys-title">À chaque console, son univers.</h1></div>
        <div className="jl-count"><strong>${String(machines.length).padStart(2, '0')}</strong>
          <span>${machines.length === 1 ? 'console' : 'consoles'}<br />installée${machines.length === 1 ? '' : 's'}</span></div>
      </div>
      ${error ? html`<p className="jl-error" role="alert">${error}</p>` : null}
      <div className="jl-scroll">
        ${machines.length
          ? html`<div className="jl-consoles">${machines.map((m) => html`<${ConsoleCard} key=${m.id} system=${m} count=${counts[m.id] ?? 0} />`)}</div>`
          : html`<div className="jl-empty"><b>Aucune console pour l’instant.</b>
              <p>Installe ta première console dans Réglages, Émulateurs & apps.</p></div>`}
        ${apps.length ? html`<${Fragment}><div className="jl-rail-head"><h2>Tes applications</h2></div>
          <div className="jl-apps">${apps.map((a) => html`<${AppCard} key=${a.id} app=${a} held=${!!heldApp(a)} onOpen=${() => openApp(a)} />`)}</div><//>` : null}
      </div>
      <${Footer} hints=${hints} />
    </section>`
  }
}
