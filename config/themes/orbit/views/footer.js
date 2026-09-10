import {isApp} from '../lib/catalog.js'

/** What the buttons do on the tab that is showing.
 *
 * Each view used to print its own row of these, under a footer that printed a
 * second row a few pixels away — two bars of hints, overlapping, saying
 * different things about the same pad. One bar, and it follows the tab. */
const hintsFor = (tab) => tab === 'library'
  ? [['← → ↑ ↓', 'Browse'], ['✕', 'Details'], ['○', 'Back'], ['△', 'Search'],
     ['L1 R1', 'Tabs'], ['R2', 'Options'], ['□', 'Inputs']]
  : tab === 'systems'
    ? [['← →', 'Browse'], ['✕', 'Open'], ['L1 R1', 'Tabs'], ['□', 'Inputs']]
    : tab === 'applications'
      ? [['← →', 'Choose'], ['✕', 'Open'], ['L1 R1', 'Tabs'], ['□', 'Inputs']]
      : [['← →', 'Browse'], ['✕', 'Select'], ['L1 R1', 'Tabs'], ['□', 'Inputs']]

export function createFooter(sdk, tabs) {
  const {html, useState, useEffect} = sdk.ui
  let counts = {consoles: 0, games: 0, apps: 0}
  const listeners = new Set()
  function update(systems, totals) {
    counts = {consoles: systems.filter(s => !isApp(s)).length,
      apps: systems.filter(isApp).length, games: totals.games}
    listeners.forEach(fn => fn(counts))
  }
  function Footer() {
    const [collection, setCollection] = useState(counts)
    const [info, setInfo] = useState(null)
    const {background} = sdk.session.use()
    const tab = tabs.useTab()
    useEffect(() => {listeners.add(setCollection); return () => listeners.delete(setCollection)}, [])
    useEffect(() => {
      let live = true
      const load = () => sdk.api.sysinfo().then(next => {if (live) setInfo(next)}).catch(() => {})
      load()
      const timer = setInterval(load, 60000)
      const offs = [sdk.system.onWsEvent('gp:connected', load), sdk.system.onWsEvent('gp:disconnected', load),
        sdk.system.onWsEvent('gp:controllers', data => {
          if (live && Array.isArray(data?.controllers)) setInfo(prev => ({...prev, controllers: data.controllers}))
        })]
      return () => {live = false; clearInterval(timer); offs.forEach(off => off())}
    }, [])
    const padName = (info?.controllers?.[0]?.name || info?.controllers?.[0]?.label || '').toLowerCase()
    const xbox = /xbox|xinput/.test(padName)
    const labels = xbox ? {'✕':'A', '○':'B', '□':'X', '△':'Y', 'L1 R1':'LB RB', 'R2':'RT', 'L2':'LT'} : {}
    return html`<footer className="console-footer" data-sessions=${background.length > 0 ? 'true' : 'false'}>
      <div className="footer-status"><span className="status-light" />
        <span>${collection.consoles} consoles · ${collection.games} games · ${collection.apps} applications</span></div>
      <div className="keyboard-hints">${hintsFor(tab).map(([key, label]) =>
        html`<span key=${label}><kbd>${labels[key] || key}</kbd> ${label}</span>`)}
        ${background.length ? html`<span><kbd>${labels.L2 || 'L2'}</kbd> Session</span>` : null}</div>
      <div className="status-bar" aria-label="Connected controllers and network">
        ${(info?.controllers || []).map((pad, i) => html`<span key=${i} className="topbar-pad" title=${pad.name || pad.label || 'Controller'}>
          <b>P${pad.player ?? i + 1}</b>${Number.isFinite(pad.level) && pad.level >= 0 ? html`<span>${pad.level}%</span>` : null}</span>`)}
        ${info?.ip ? html`<span className="topbar-ip">⌁ ${info.ip}</span>` : null}
      </div>
    </footer>`
  }
  return {Component: Footer, update}
}
