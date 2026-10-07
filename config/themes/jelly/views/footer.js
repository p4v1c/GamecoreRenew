/** The hint bar under every Jelly screen: what each button does here, and the
 * pads that are actually connected. Each screen passes its own hints, so the
 * bar never offers a button that does nothing on that screen. */
export function createFooter(sdk) {
  const {html, useState, useEffect} = sdk.ui
  const PadKey = sdk.ui.PadKey || (({k}) => html`<kbd>${k}</kbd>`)

  // One poll for every mounted footer: Home and the library both draw one.
  let info = null
  const listeners = new Set()
  let started = false
  const set = (next) => { info = next; listeners.forEach((fn) => fn(info)) }
  const load = () => sdk.api.sysinfo().then(set).catch(() => {})
  const start = () => {
    if (started) return
    started = true
    load()
    setInterval(load, 60000)
    sdk.system.onWsEvent('gp:connected', load)
    sdk.system.onWsEvent('gp:disconnected', load)
    sdk.system.onWsEvent('gp:controllers', (d) => {
      if (Array.isArray(d?.controllers)) set({...info, controllers: d.controllers})
    })
  }

  // The Gamepad API sees every pad; sysinfo only sees the ones reporting a
  // battery, so it is used for the levels and nothing else.
  const connected = () => (navigator.getGamepads ? [...navigator.getGamepads()] : []).filter(Boolean)

  // Player 1 shows the active profile's name; a host without `sdk.players` says P1.
  const usePadLabel = sdk.players?.useLabel ?? (() => (n) => `P${n}`)
  return function Footer({hints}) {
    const padLabel = usePadLabel()
    const [now, setNow] = useState(info)
    const [count, setCount] = useState(() => connected().length)
    const {background} = sdk.session.use()
    useEffect(() => {
      start()
      listeners.add(setNow)
      setNow(info)
      const recount = () => setCount(connected().length)
      const offs = [sdk.input.onGp('gp:connected', recount), sdk.input.onGp('gp:disconnected', recount)]
      return () => { listeners.delete(setNow); offs.forEach((off) => off()) }
    }, [])
    const levels = Array.isArray(now?.controllers) ? now.controllers : []
    const pads = Array.from({length: Math.max(count, levels.length)}, (_, i) => levels[i] || {player: i + 1})
    const all = background.length ? [...hints, ['PS ×2', 'Paused game']] : hints
    return html`<footer className="jl-footer">
      <div className="jl-hints">
        <span className="jl-footer-label">Your turn</span>
        ${all.map(([k, label]) => html`<span key=${label} className="jl-hint"><${PadKey} k=${k} />${label}</span>`)}
      </div>
      <div className="jl-status" aria-label="Controllers and network">
        ${pads.length
          ? pads.map((p, i) => html`<span key=${i} className="jl-pad" title=${p.name || p.label || 'Controller'}>
              <i className="jl-dot" />${padLabel(p.player ?? i + 1)}${Number.isFinite(p.level) && p.level >= 0 ? `, ${p.level} %` : ''}</span>`)
          : html`<span className="jl-pad jl-pad-none">No controller</span>`}
        ${now?.ip ? html`<span className="jl-ip">${now.ip}</span>` : null}
      </div>
    </footer>`
  }
}
