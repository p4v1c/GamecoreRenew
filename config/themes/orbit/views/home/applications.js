import {isApp, systemName, appStyle, packLogo} from '../../lib/catalog.js'

export function createApplicationsTab({sdk, tabs, sessions, backdrop, Art, svg, hooks}) {
  const {html, useState, useEffect, useMemo} = sdk.ui
  const {useHomeKeys} = hooks

  // ── the Applications tab ──────────────────────────────────────────────────

  function ApplicationsTab({systems}) {
    const apps = useMemo(() => systems.filter(isApp), [systems])
    const [idx, setIdx] = useState(0)
    const {background} = sdk.session.use()
    const at = Math.min(idx, Math.max(0, apps.length - 1))
    const app = apps[at]
    const move = (d) => setIdx((i) => (i + d + apps.length) % Math.max(1, apps.length))
    const open = () => {
      if (!app) return
      const held = sessions.heldMatch(background, app.id, app.id)
      if (held) {sdk.session.resume(held.session).catch(() => {}); return}
      sdk.defaults.launchApp(app)
    }
    useHomeKeys(move, open, 'applications')
    const screen = sdk.nav.use(s => s.screen)
    useEffect(() => {if (screen === 'home' && tabs.get() === 'applications') backdrop?.select({kind: 'app', accent: appStyle(app).color})}, [app?.id, screen])

    if (!app) {
      return html`<section id="applications-view" className="collection-view applications-view">
        <div className="page-heading"><div><p className="eyebrow">YOUR LIVING ROOM. EVERY WORLD.</p>
          <h1>No applications yet.</h1></div></div>
        <p className="mock-footnote">Settings → Catalog installs Steam, YouTube, Twitch and Stremio.</p></section>`
    }
    const s = appStyle(app)
    const held = sessions.heldMatch(background, app.id, app.id)
    return html`<section id="applications-view" className="collection-view applications-view"
                         style=${{'--application-accent': s.color}} aria-labelledby="applications-title">
      <div className="page-heading"><div><p className="eyebrow">YOUR LIVING ROOM. EVERY WORLD.</p>
        <h1 id="applications-title">Your apps.</h1></div>
        <span className="page-count">${apps.length} pack${apps.length === 1 ? '' : 's'}</span></div>
      <div className="application-rail" aria-label="Choose an app">
        ${apps.map((a, i) => {
          const st = appStyle(a)
          return html`<button key=${a.id}
            className=${`application-tile ${i === at ? 'selected' : ''}`}
            data-active=${i === at ? 'true' : 'false'} aria-pressed=${String(i === at)}
            style=${{'--tile-color': st.color, '--app-tile-color': st.tile, '--app-logo-scale': st.scale}}
            aria-label=${`Select ${systemName(a)}`}
            onClick=${() => (i === at ? open() : setIdx(i))}>
            <span className="application-tile-image"><${Art} src=${packLogo(a)} alt="" />
              ${sessions.heldMatch(background, a.id, a.id)
                ? html`<span className="session-badge">IN BACKGROUND</span>` : null}</span>
            <span className="application-tile-title">${systemName(a)}</span><small>${st.category}</small>
          </button>`
        })}
      </div>
      <div className="application-feature">
        <div className="application-copy">
          <p className="eyebrow"><span className="application-category">${s.category}</span>
            <span className="dot" />${s.edition}</p>
          <h2>${systemName(app)}</h2>
          <p className="application-description">${s.description}</p>
          <button className="primary-button" onClick=${open}>${svg('play')}${
            held ? 'Resume' : 'Open'} ${systemName(app)}<span className="application-confirm">✕</span></button>
          <span className="application-pack">GameCore pack · ${app.id}</span>
        </div>
        <div className="application-emblem" aria-hidden="true">
          <div className="application-emblem-orbit" />
          <div className="application-emblem-tile"
               style=${{'--app-tile-color': s.tile, '--app-logo-scale': s.scale}}>
            <${Art} src=${packLogo(app)} alt="" /></div>
          <span>${s.edition}</span>
        </div>
      </div>
    </section>`
  }

  return ApplicationsTab
}
