import {TABS} from '../lib/tabs.js'

/** The mockup header: brand, four tabs, power, settings and clock. */
export function createTopBar(sdk, tabs, systemsRef) {
  const {html, useState, useEffect} = sdk.ui

  return function TopBar({onSettings, onPower}) {
    const tab = tabs.useTab()
    const [clock, setClock] = useState('')

    useEffect(() => {
      const tick = () => setClock(new Date().toLocaleTimeString('en-GB',
        {hour: '2-digit', minute: '2-digit'}))
      tick()
      const timer = setInterval(tick, 15000)
      return () => clearInterval(timer)
    }, [])

    return html`<header className="topbar">
      <button className="brand" aria-label="GameCore, home"
              onClick=${() => tabs.go('home', systemsRef.current)}>
        <svg viewBox="0 0 36 36" aria-hidden="true"><path
          d="M19 3 5 11v15l13 8 13-8V15H18v7h6v1l-6 4-6-4V15l10-6z" fill="currentColor" /></svg>
        <span>GAMECORE<i>ORBIT</i></span>
      </button>
      <nav className="navigation" aria-label="Main navigation">
        ${TABS.map(([id, label]) => html`<button key=${id}
          className=${`nav-item ${tab === id ? 'active' : ''}`}
          aria-current=${tab === id ? 'page' : undefined}
          onClick=${() => tabs.go(id, systemsRef.current)}>${label}</button>`)}
      </nav>
      <div className="utilities">
        <button className="icon-button" onClick=${onPower} aria-label="Power menu">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2v9m-5-7a9 9 0 1 0 10 0" /></svg>
        </button>
        <button className="icon-button" onClick=${onSettings} aria-label="GameCore settings">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path
            d="m9 3-.7 2.6-2.4 1-2.4-.7-2 3.5 1.8 1.9v2.8l-1.8 1.9 2 3.5 2.4-.7 2.4 1L9 22h4l.7-2.7 2.4-1 2.4.7 2-3.5-1.8-1.9v-2.8l1.8-1.9-2-3.5-2.4.7-2.4-1L13 3z"
            transform="translate(1 -1) scale(.95)" /><circle cx="11.5" cy="11" r="3" /></svg>
        </button>
        <time>${clock}</time>
      </div>
    </header>`
  }
}
