import {TABS} from '../lib/tabs.js'
import {mark} from '../lib/drawings.js'

const ICONS = {
  search: '<circle cx="10.5" cy="10.5" r="6"/><path d="m15 15 5 5"/>',
  settings: '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="2.6"/><circle cx="16" cy="17" r="2.6"/>',
  power: '<path d="M12 3v8"/><path d="M6.6 6.6a8 8 0 1 0 10.8 0"/>',
}

/** Brand, the three tabs between their shoulder keys, and the corner buttons.
 * Also where the shell's Settings and Power doors are handed over, so a Jelly
 * screen can open them for a player with no pointer. */
export function createTopBar(sdk, {tabs, actions}) {
  const {html, useState, useEffect} = sdk.ui
  const PadKey = sdk.ui.PadKey || (({k}) => html`<kbd>${k}</kbd>`)
  const icon = (name) => html`<svg viewBox="0 0 24 24" aria-hidden="true"
    dangerouslySetInnerHTML=${{__html: ICONS[name]}} />`

  return function TopBar({onSettings, onPower}) {
    const tab = tabs.useTab()
    const screen = sdk.nav.use((s) => s.screen)
    const [clock, setClock] = useState('')
    actions.settings = onSettings
    actions.power = onPower

    useEffect(() => {
      const tick = () => setClock(new Date().toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'}))
      tick()
      const t = setInterval(tick, 15000)
      return () => clearInterval(t)
    }, [])

    const lit = screen === 'library' ? 'consoles' : tab
    return html`<header className="jl-topbar">
      <button type="button" className="jl-brand" aria-label="GameCore, accueil" onClick=${() => tabs.go('play')}>
        <span className="jl-brand-mark" dangerouslySetInnerHTML=${{__html: mark()}} />
        <span className="jl-brand-word">GameCore<small>Jelly edition</small></span>
      </button>
      <nav className="jl-tabs" aria-label="Navigation principale">
        <${PadKey} k="L1" />
        ${TABS.map(([id, label]) => html`<button type="button" key=${id}
          className=${`jl-tab ${lit === id ? 'is-on' : ''}`} aria-current=${lit === id ? 'page' : undefined}
          onClick=${() => tabs.go(id)}>${label}</button>`)}
        <${PadKey} k="R1" />
      </nav>
      <div className="jl-top-actions">
        <button type="button" className="jl-icon" aria-label="Rechercher" onClick=${() => actions.search?.()}>${icon('search')}</button>
        <button type="button" className="jl-icon" aria-label="Réglages" onClick=${onSettings}>${icon('settings')}</button>
        <button type="button" className="jl-icon" aria-label="Alimentation" onClick=${onPower}>${icon('power')}</button>
        <time className="jl-clock">${clock}</time>
      </div>
    </header>`
  }
}
