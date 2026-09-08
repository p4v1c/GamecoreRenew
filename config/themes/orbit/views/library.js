import {systemName} from '../lib/artwork.js'

export function createLibrary(sdk, artwork, sessions, Footer) {
  const {html, useState, useEffect, useRef} = sdk.ui
  return function Library(props) {
    const {systemId, system, games, totalCount, selectedIdx, detailGame, sort, sortKeys, sortLabels, search,
      loading, loadError, launching, color, onSelect, onSearch, onSort, onLaunch, onBack, onRetry, Cover, Meta} = props
    const [art, setArt] = useState(null)
    const list = useRef(null)
    const screen = sdk.nav.use((s) => s.screen)
    const {background} = sdk.session.use()
    const selected = games[selectedIdx]
    const title = (g) => g?.display_name || (g ? sdk.format.gameName(g.filename) : '')
    // A game's session is keyed by its ROM filename — routers/games.py.
    const heldFor = (g) => (g ? sessions.heldMatch(background, g.filename, systemId) : null)
    const held = heldFor(selected)
    useEffect(() => {list.current?.querySelector('[data-active="true"]')?.scrollIntoView({block: 'nearest', behavior: 'smooth'})}, [selectedIdx, search, screen])
    useEffect(() => {
      setArt(null)
      if (!detailGame || !systemId || screen !== 'library') return
      let live = true
      sdk.api.media.list(systemId, detailGame.filename).then((data) => {
        const type = ['fanart', 'screenshot-gameplay', 'screenshot-title'].find((key) => data.media?.[key]?.kind === 'image')
        if (live && type) setArt({key: `${systemId}:${detailGame.filename}`, url: sdk.api.media.url(systemId, detailGame.filename, type)})
      }).catch(() => {})
      return () => {live = false}
    }, [systemId, detailGame?.filename, screen])
    const artUrl = art?.key === `${systemId}:${detailGame?.filename}` ? art.url : null
    return html`<main className="orbit-library">
      ${artUrl ? html`<img className="orbit-game-backdrop" src=${artUrl} alt="" onError=${() => setArt(null)} />` : null}
      <div className="orbit-library-heading"><div><span className="orbit-eyebrow">YOUR GAME LIBRARY</span><h2>${systemName(system)}</h2></div>
        <div className="orbit-library-tools">
          <!-- Searching is the host's. Triangle opens its on-screen keyboard,
               which owns the modal stack and the d-pad; this field is for a
               mouse on a desk and calls the same onSearch the keyboard does.
               Orbit used to open a SECOND keyboard of its own from a button
               here — the same host component, styled the same, reachable with
               a pointer and by nothing else. On a console that is a dead
               control, and two modals over one screen if both ever opened. -->
          <label className="orbit-search"><span className="orbit-eyebrow">SEARCH <kbd>△ / Y</kbd></span>
            <input value=${search} placeholder="Game title" aria-label="Search your game library"
                   onChange=${(e) => onSearch(e.target.value)} /></label>
          <div className="orbit-sort" aria-label="Sort games">${sortKeys.map((key) => html`<button key=${key} data-active=${sort === key ? 'true' : 'false'} onClick=${() => onSort(key)}>${sortLabels[key]}</button>`)}</div>
          <button className="orbit-icon-button" onClick=${onBack} aria-label="Back to consoles">←</button></div></div>
      ${search ? html`<div className="orbit-search-query">Results for “${search}” <button onClick=${() => onSearch('')}>Clear search</button></div>` : null}
      ${loadError ? html`<section className="orbit-empty"><h1>Could not load this library.</h1><button className="orbit-button orbit-primary" onClick=${onRetry}>Try again</button></section>`
      : loading ? html`<section className="orbit-empty" role="status"><span className="orbit-loader" /><h2>Opening your collection…</h2></section>`
      : !games.length ? html`<section className="orbit-empty"><h1>${search ? 'No games found.' : 'Room for new adventures.'}</h1><p>${search ? 'Try another title, or clear your search with Triangle / Y.' : 'Add games to this system to see them here.'}</p></section>`
      : html`<div className="orbit-library-body"><div className="orbit-game-list" ref=${list} aria-label="Games">
        ${games.map((game, i) => html`<button className="orbit-game-row" key=${game.filename} data-active=${i === selectedIdx ? 'true' : 'false'}
          aria-current=${i === selectedIdx ? 'true' : undefined} onFocus=${() => onSelect(i)} onClick=${() => onSelect(i)}>
          <div className="orbit-game-thumb"><${Cover} systemId=${systemId} filename=${game.filename} color=${color} /></div>
          <span><strong>${title(game)}</strong><small>${heldFor(game) ? '● Suspended' : game.ext?.replace(/^\./, '').toUpperCase() || 'Game'}</small></span>
        </button>`)}
      </div><section className="orbit-game-feature">
        ${detailGame ? html`<div className="orbit-game-detail" key=${`${systemId}:${detailGame.filename}`}>
          <div className="orbit-hero-cover"><${Cover} systemId=${systemId} filename=${detailGame.filename} color=${color} /></div>
          <div className="orbit-game-copy"><span className="orbit-eyebrow">${systemName(system)}</span><h1>${title(detailGame)}</h1>
            <div className="orbit-meta"><${Meta} systemId=${systemId} filename=${detailGame.filename} extChip=${null} color=${color} /></div></div>
        </div>` : null}
        <div className="orbit-actions">
          ${held
            ? html`<button className="orbit-button orbit-primary" onClick=${() => sessions.available() && sdk.session.resume(held.session).catch(() => {})}>▶ Resume <kbd>L2</kbd></button>`
            : html`<button className="orbit-button orbit-primary" disabled=${launching || !selected} onClick=${onLaunch}>${launching ? 'Launching…' : '▶ Play'} <kbd>✕ / A</kbd></button>`}
        </div>
        ${launching ? html`<p role="status" className="orbit-muted">Opening ${title(selected)} · Back to cancel</p>` : null}
      </section></div>`}
      <${Footer} library=${true} summary=${`${games.length} of ${totalCount} games`} />
    </main>`
  }
}
