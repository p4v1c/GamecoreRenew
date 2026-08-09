/**
 * One system tile.
 *
 * The default frontend has this as components/HomeScreen/SystemCard.tsx; a
 * theme supplies only the *view* of a screen, so there is no HomeScreen/ folder
 * here — this is the one piece worth its own file.
 *
 * It is also the file that found the first SDK hole. The colour comes from
 * `sdk.format.systemColor`, which did not exist: the resolution was a private
 * getColor() inside SystemCard, and `SystemEntry.color` is optional. A theme
 * reading `system.color` directly draws every system the catalogue does not
 * describe in the house purple, which reads as broken rather than as plain.
 */
export const createCard = (sdk) => {
  const { html } = sdk.ui
  const { systemColor, hexToRgb, time, date } = sdk.format

  return ({ system, playtime, gameCount, focused, onClick }) => {
    const color = systemColor(system)
    const rgb = hexToRgb(color)

    return html`
      <div class="dr-card" data-on=${focused ? '1' : '0'} onClick=${onClick}
           style=${{
             background: focused ? `rgba(${rgb}, 0.12)` : 'rgba(255,255,255,0.04)',
             border: focused ? `1px solid ${color}60` : '1px solid rgba(255,255,255,0.07)',
             boxShadow: focused ? `0 12px 32px rgba(${rgb}, 0.25)` : 'none',
           }}>
        <div class="dr-card-head">
          <div class="dr-card-icon"
               style=${{ background: focused ? color : `rgba(${rgb}, 0.2)` }}>
            ${system.iconPath
              ? html`<img src=${system.iconPath} alt="" class="dr-card-img" />`
              : html`<span class="dr-card-glyph">${(system.label || system.id).slice(0, 2).toUpperCase()}</span>`}
          </div>
          <div class="dr-card-name">
            <b>${system.label || system.id}</b>
            <i>${system.platform || system.type || system.kind}</i>
          </div>
        </div>
        <div class="dr-card-stats">
          <span>${gameCount == null ? '—' : `${gameCount} games`}</span>
          ${playtime?.total_secs
            ? html`<span style=${{ color }}>${time(playtime.total_secs)}</span>`
            : null}
        </div>
        ${playtime?.last_played
          ? html`<div class="dr-card-last">Last played ${date(playtime.last_played)}</div>`
          : null}
      </div>`
  }
}
