/**
 * The status bar: clock, host, storage, controller batteries.
 *
 * Everything here comes from `sdk.api.sysinfo` and the WebSocket, both of which
 * a theme has in full — this file needed no SDK change, which is the answer you
 * want from a surface that was designed rather than discovered.
 *
 * The battery pill is drawn here rather than taken from the host, because it is
 * markup. The controller screen gets the host's version handed to it as
 * `Battery` precisely so the two agree; this one is the theme's own.
 */
export const createTopBar = (sdk) => {
  const { html, useState, useEffect } = sdk.ui

  return ({ onSettings, onPower }) => {
    const [info, setInfo] = useState(null)
    const [clock, setClock] = useState('')

    useEffect(() => {
      const tick = () => setClock(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
      tick()
      const t = setInterval(tick, 20000)
      return () => clearInterval(t)
    }, [])

    useEffect(() => {
      let alive = true
      const load = () => sdk.api.sysinfo.get()
        .then(r => { if (alive) setInfo(r) })
        .catch(() => {})
      load()
      const t = setInterval(load, 30000)
      // The pad's battery changes between polls, and the backend says so.
      const off = sdk.system.onWsEvent('gp:battery', load)
      return () => { alive = false; clearInterval(t); off() }
    }, [])

    const pads = info?.controllers ?? []

    return html`
      <div class="dr-topbar">
        <div class="dr-brand">
          <span class="dr-brand-mark">◆</span>
          <span class="dr-brand-name">GAMECORE</span>
        </div>

        <div class="dr-top-mid">
          ${info?.ip ? html`<span class="dr-pill">${info.ip}</span>` : null}
          ${info?.storage
            ? html`<span class="dr-pill">${info.storage.free_h ?? ''} free</span>`
            : null}
          ${pads.map(c => html`
            <span key=${c.player ?? c.label} class="dr-pill dr-batt"
                  data-low=${(c.battery ?? 100) <= 20 ? '1' : '0'}>
              ${c.player != null ? html`<b>P${c.player}</b>` : null}
              ${c.charging ? '⚡' : ''}${c.battery == null ? '—' : `${c.battery}%`}
            </span>`)}
        </div>

        <div class="dr-top-right">
          <span class="dr-clock">${clock}</span>
          <button class="dr-tbtn" onClick=${onSettings}>⚙ Settings</button>
          <button class="dr-tbtn dr-tbtn-danger" onClick=${onPower}>⏻ Power</button>
        </div>
      </div>`
  }
}
