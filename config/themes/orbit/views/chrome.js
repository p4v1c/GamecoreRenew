export function createChrome(sdk, sessions) {
  const {html, useState, useEffect} = sdk.ui
  let info = null
  const listeners = new Set()
  const publish = (next) => {info = next; listeners.forEach((fn) => fn(next))}
  function Status() {
    const [value, setValue] = useState(info)
    const pad = sdk.input.useGamepadState()
    useEffect(() => {listeners.add(setValue); setValue(info); return () => listeners.delete(setValue)}, [])
    const controllers = value?.controllers || []
    return html`<div className="orbit-status" aria-label="Connection status">
      ${controllers.map((c, i) => html`<span className="orbit-pad" key=${`${c.player}-${c.name}-${i}`} title=${c.name || c.label || 'Connected controller'}>
        <b>${c.player != null ? `P${c.player}` : 'Pad'}</b><span aria-hidden="true">⌘</span>
        ${Number.isFinite(c.level) && c.level >= 0 ? html`<span className="orbit-pad"><span className="orbit-battery" role="img" aria-label=${`${c.level}% battery`}
          style=${{'--orbit-battery': `${Math.max(0, Math.min(100, c.level))}%`}} /><span>${c.charging ? 'ϟ ' : ''}${c.level}%</span></span>` : null}
      </span>`)}
      ${pad.connected && !controllers.length ? html`<span>Controller connected</span>` : null}
      ${value?.ip ? html`<span className="orbit-ip" title="Network address">⌁ ${value.ip}</span>` : null}
    </div>`
  }
  function TopBar({onSettings, onPower}) {
    const [clock, setClock] = useState('')
    const screen = sdk.nav.use((s) => s.screen)
    useEffect(() => {
      let live = true, timer
      const load = async () => {
        try {const next = await sdk.api.sysinfo(); if (live) publish(next)} catch {}
        if (live) {clearTimeout(timer); timer = setTimeout(load, info ? 60000 : 5000)}
      }
      load()
      const offs = [sdk.system.onWsEvent('gp:connected', load), sdk.system.onWsEvent('gp:disconnected', load),
        sdk.system.onWsEvent('gp:controllers', (data) => {if (live && Array.isArray(data?.controllers)) publish({...info, controllers: data.controllers})})]
      return () => {live = false; clearTimeout(timer); offs.forEach((off) => off())}
    }, [])
    useEffect(() => {
      const tick = () => setClock(new Date().toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit'}))
      tick(); const timer = setInterval(tick, 15000); return () => clearInterval(timer)
    }, [])
    return html`<header className="orbit-topbar">
      <button className="orbit-brand" aria-label="GameCore home" onClick=${sdk.nav.goHome}><span className="orbit-brand-mark">G</span><span>GAMECORE<small>O R B I T</small></span></button>
      <nav aria-label="Collection"><button className="orbit-tab" data-active=${screen === 'home' ? 'true' : 'false'} onClick=${sdk.nav.goHome}>Consoles & apps</button>
        ${screen === 'library' ? html`<span className="orbit-tab" data-active="true">Game library</span>` : null}</nav>
      <div className="orbit-tools"><button className="orbit-icon-button" onClick=${onPower} title="Power · Share / View" aria-label="Power">⏻</button>
        <button className="orbit-icon-button" onClick=${onSettings} title="Settings · Options / Menu" aria-label="Settings">⚙</button><time>${clock}</time></div>
    </header>`
  }
  function Footer({library = false, summary = ''}) {
    // The session hint appears only when there IS a suspended session: L2 does
    // nothing otherwise, and a permanent hint for a key that usually does
    // nothing is how a player learns to stop reading the hint bar.
    const held = sdk.session.use().background.length > 0
    return html`<footer className="orbit-footer"><div className="orbit-footer-line"><div className="orbit-hints">
      <span><kbd>${library ? '↑ ↓' : '← →'}</kbd> Browse</span><span><kbd>✕ / A</kbd> Select</span>
      ${library ? html`<span className="orbit-hint-group"><span><kbd>○ / B</kbd> Back</span><span><kbd>△ / Y</kbd> Search</span><span><kbd>L1 R1</kbd> Sort</span><span><kbd>R2</kbd> Options</span></span>` : null}
      <span><kbd>□ / X</kbd> Inputs</span>${held ? html`<span><kbd>L2</kbd> Suspended session</span>` : null}
      <span><kbd>Menu</kbd> Settings</span></div><${Status} /></div>
      ${summary ? html`<div className="orbit-summary">${summary}</div>` : null}</footer>`
  }
  return {TopBar, Footer}
}
