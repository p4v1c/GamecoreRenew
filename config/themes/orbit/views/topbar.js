import {TABS} from '../lib/tabs.js'

/** The header: the mark, the four tabs, and the box's own state on the right.
 *
 * The controller roster and the address arrive by push — `gp:connected`,
 * `gp:disconnected`, `gp:controllers` — rather than by polling, because
 * re-asking every second for four numbers that change once an hour is how a
 * launcher ends up warm to the touch.
 */
export function createTopBar(sdk, tabs, systemsRef) {
  const {html, useState, useEffect} = sdk.ui

  return function TopBar({onSettings, onPower}) {
    const tab = tabs.useTab()
    const [info, setInfo] = useState(null)
    const [clock, setClock] = useState('')
    const pad = sdk.input.useGamepadState()

    useEffect(() => {
      let live = true, timer
      const load = async () => {
        try {const next = await sdk.api.sysinfo(); if (live) setInfo(next)} catch { /* keep the last */ }
        if (live) {clearTimeout(timer); timer = setTimeout(load, 60000)}
      }
      load()
      const offs = [
        sdk.system.onWsEvent('gp:connected', load),
        sdk.system.onWsEvent('gp:disconnected', load),
        sdk.system.onWsEvent('gp:controllers', (data) => {
          if (live && Array.isArray(data?.controllers)) {
            setInfo((prev) => ({...(prev || {}), controllers: data.controllers}))
          }
        }),
      ]
      return () => {live = false; clearTimeout(timer); offs.forEach((off) => off())}
    }, [])

    useEffect(() => {
      const tick = () => setClock(new Date().toLocaleTimeString('en-GB',
        {hour: '2-digit', minute: '2-digit'}))
      tick()
      const timer = setInterval(tick, 15000)
      return () => clearInterval(timer)
    }, [])

    const controllers = info?.controllers || []
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
        ${controllers.map((c, i) => html`<span className="topbar-pad"
          key=${`${c.player}-${i}`} title=${c.name || c.label || 'Connected controller'}>
          <b>P${c.player ?? i + 1}</b>
          ${Number.isFinite(c.level) && c.level >= 0
            ? html`<span className="topbar-battery"><i style=${{
                width: `${Math.max(0, Math.min(100, c.level))}%`}} /></span>` : null}
        </span>`)}
        ${!controllers.length && pad.connected
          ? html`<span className="topbar-pad"><b>P1</b></span>` : null}
        ${info?.ip ? html`<span className="topbar-ip" title="Network address">⌁ ${info.ip}</span>` : null}
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
