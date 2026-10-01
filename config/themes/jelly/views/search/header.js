import {isApp, systemMark} from '../../lib/catalog.js'
import {ZONES} from './zones.js'

const HINTS = [['← → ↑ ↓', 'Naviguer'], ['✕', 'Choisir'], ['□', 'Effacer'], ['L2', 'Tout vider'],
  ['△', 'Clavier ou jeux'], ['L1 R1', 'Zones']]

/** The search's frame: title, the typed query, zone tabs, filters, hint bar. */
export function createSearchFrame(sdk, {Icon}) {
  const {html} = sdk.ui
  const {Fragment} = sdk.ui.React
  const PadKey = sdk.ui.PadKey || (({k}) => html`<kbd>${k}</kbd>`)

  function Header({query, zone, ready, gamesUsable, onZone, onClose}) {
    return html`<${Fragment}>
      <header className="jl-search-head">
        <div><span className="jl-eyebrow">Cherche. Trouve. Joue.</span><h2 id="jl-search-title">La bonne pioche.</h2></div>
        <button type="button" className="jl-close" aria-label="Fermer la recherche" onClick=${onClose}>×</button>
      </header>
      <div className="jl-query" aria-live="polite">
        <${Icon} name="search" className="jl-query-icon" />
        <span className=${`jl-query-text ${query ? '' : 'is-empty'}`}>${query || 'Un jeu, une console…'}</span>
        ${zone === 'keys' ? html`<i className="jl-caret" aria-hidden="true" />` : null}
        <span className="jl-live">${ready ? 'En direct' : 'Chargement…'}</span>
      </div>
      <nav className="jl-zones" aria-label="Zones de recherche"><${PadKey} k="L1" />
        ${ZONES.map(([id, label], i) => html`<button type="button" key=${id} className=${`jl-zone ${zone === id ? 'is-on' : ''}`}
          disabled=${id === 'games' && !gamesUsable} aria-pressed=${String(zone === id)}
          onClick=${() => onZone(id)}><small>0${i + 1}</small>${label}</button>`)}<${PadKey} k="R1" /></nav>
    <//>`
  }

  function Foot({zone}) {
    return html`<footer className="jl-search-foot">
      ${[...HINTS, ['○', zone === 'keys' ? 'Fermer' : 'Clavier']].map(([k, v]) =>
        html`<span key=${k}><${PadKey} k=${k} />${v}</span>`)}
    </footer>`
  }

  /** One chip per console that has games, plus all and favourites. */
  function Filters({games, systems, filter, onFilter}) {
    const chip = (id, label) => html`<button type="button" key=${id} data-nav=${`sf-${id}`}
      className=${`jl-chip ${filter === id ? 'is-on' : ''}`} aria-pressed=${String(filter === id)}
      onClick=${() => onFilter(id)}>${label}</button>`
    const machines = systems.filter((s) => !isApp(s) && games.some((g) => g.systemId === s.id))
    return html`<${Fragment}>${chip('all', 'Tout')}${machines.map((m) => chip(m.id, systemMark(m)))}
      ${chip('fav', html`<${Icon} name="star" filled=${filter === 'fav'} />Favoris`)}<//>`
  }

  return {Header, Foot, Filters}
}
