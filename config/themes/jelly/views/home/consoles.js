import {
  isApp, systemName, systemMark, systemMaker, systemYear, coverColor, consoleArt, packLogo,
  appStyle, plural,
} from '../../lib/catalog.js'
import {createSpatial, homeOwnsPad} from '../../lib/spatial.js'

/** Consoles: one card per installed console, then the applications.
 * ✕ on a console opens its library (the host's screen); on an application,
 * launches it, or resumes it when it is already in the background. */
export function createConsolesTab(sdk, {tabs, art, Footer, hints}) {
  const {html, useState, useRef, useMemo} = sdk.ui
  const {Fragment} = sdk.ui.React
  const useSpatial = createSpatial(sdk)
  const {Picture} = art

  return function ConsolesTab({systems, counts, onSearch}) {
    const root = useRef(null)
    const [error, setError] = useState('')
    const {background} = sdk.session.use()
    const machines = useMemo(() => systems.filter((s) => !isApp(s)), [systems])
    const apps = useMemo(() => systems.filter(isApp), [systems])

    const openApp = (app) => {
      setError('')
      const held = background.find((s) => s.systemId === app.id && s.gameKey === app.id)
      const run = held ? sdk.session.resume(held.session) : sdk.defaults.launchApp(app)
      Promise.resolve(run).catch((e) => setError(e?.message || `${systemName(app)} n’a pas pu s’ouvrir.`))
    }

    useSpatial(root, {
      allowed: () => homeOwnsPad(sdk) && tabs.get() === 'consoles',
      initial: '.jl-consoles [data-nav]',
      keys: {l1: () => tabs.step(-1), r1: () => tabs.step(1), y: onSearch,
        back: () => tabs.go('play')},
    }, [systems.length])

    return html`<section className="jl-page jl-consoles-page" ref=${root} aria-labelledby="jl-sys-title">
      <div className="jl-head">
        <div><span className="jl-eyebrow">Les consoles</span>
          <h1 id="jl-sys-title">À chaque console, son univers.</h1></div>
        <div className="jl-count"><strong>${String(machines.length).padStart(2, '0')}</strong>
          <span>${machines.length === 1 ? 'console' : 'consoles'}<br />installée${machines.length === 1 ? '' : 's'}</span></div>
      </div>
      ${error ? html`<p className="jl-error" role="alert">${error}</p>` : null}
      <div className="jl-scroll">
        ${machines.length ? html`<div className="jl-consoles">
            ${machines.map((m) => html`<button type="button" key=${m.id} className="jl-console"
                data-nav=${`c-${m.id}`} style=${{'--cover': coverColor(sdk, m)}}
                aria-label=${`${systemName(m)}, ${plural(counts[m.id] ?? 0, 'jeu', 'jeux')}`}
                onClick=${() => sdk.nav.goLibrary(m.id)}>
              <span className="jl-console-stage">
                <span className="jl-console-tag">${systemMark(m)}</span>
                <span className="jl-console-ghost" aria-hidden="true">${systemMark(m)}</span>
                <${Picture} className="jl-console-photo" src=${consoleArt(sdk, m)} mark=${systemMark(m)} />
              </span>
              <span className="jl-console-caption">
                <b>${systemName(m)}</b>
                <small>${plural(counts[m.id] ?? 0, 'jeu', 'jeux')} à retrouver${
                  systemMaker(m) ? ` · ${systemMaker(m)}${systemYear(m) ? ` ${systemYear(m)}` : ''}` : ''}</small>
                <span className="jl-arrow" aria-hidden="true">↗</span>
              </span>
            </button>`)}
          </div>`
          : html`<div className="jl-empty"><b>Aucune console pour l’instant.</b>
            <p>Réglages → Émulateurs & apps installe ta première console.</p></div>`}

        ${apps.length ? html`<${Fragment}><div className="jl-rail-head"><h2>Tes applications</h2></div>
          <div className="jl-apps">
            ${apps.map((a) => {
              const st = appStyle(a)
              const held = background.some((s) => s.systemId === a.id && s.gameKey === a.id)
              return html`<button type="button" key=${a.id} className="jl-app" data-nav=${`a-${a.id}`}
                  style=${{'--cover': st.color}} aria-label=${`Ouvrir ${systemName(a)}`}
                  onClick=${() => openApp(a)}>
                <span className="jl-app-logo"><${Picture} src=${packLogo(a)} mark=${systemMark(a)} /></span>
                <span className="jl-app-text"><b>${systemName(a)}</b><small>${st.category}</small></span>
                ${held ? html`<span className="jl-badge">En pause</span>` : null}
              </button>`
            })}
          </div><//>` : null}
      </div>
      <${Footer} hints=${hints} />
    </section>`
  }
}
