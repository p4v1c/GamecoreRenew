/**
 * The power menu — DESIGN-BRIEF.md §3.7.
 *
 * One deviation from the brief, deliberate: it says Scan mapping does not
 * belong here. On this box it does, and the rows come from the host anyway —
 * this file renders whatever it is handed. Behaviour is not a theme's to
 * change, least of all the shutdown flow.
 *
 * Props: frontend/src/components/modals/power/types.ts
 */
const ICONS = {
  scan: 'M4 7V5a1 1 0 0 1 1-1h2M20 7V5a1 1 0 0 0-1-1h-2M4 17v2a1 1 0 0 0 1 1h2M20 17v2a1 1 0 0 1-1 1h-2M3 12h18',
  restart: 'M3 12a9 9 0 1 0 3-6.7M3 4v5h5',
  shutdown: 'M12 3v9M6.3 6.3a9 9 0 1 0 11.4 0',
}

export const createPowerView = (sdk) => {
  const { html } = sdk.ui

  return ({ options, focusIdx, confirmId, pendingId, scanning, scanResult, onActivate, onCancel }) => {
    const busy = pendingId !== null
    return html`
      <div class="sm-modal-wrap sm-power-wrap"
           onClick=${(e) => { if (e.target === e.currentTarget && !busy) onCancel() }}>
        <div class="sm-panel sm-power" data-busy=${busy ? '1' : '0'}>
          <div class="sm-panel-title">SYSTEM</div>

          ${options.map((o, i) => {
            const pending = pendingId === o.id
            const isScan = o.id === 'scan'
            const pulsing = pending || (isScan && scanning)
            return html`
              <div key=${o.id} class="sm-power-row"
                   data-on=${i === focusIdx ? '1' : '0'}
                   data-confirm=${confirmId === o.id ? '1' : '0'}
                   data-dim=${busy && !pending ? '1' : '0'}
                   style=${{ '--row-accent': o.color }}
                   onClick=${() => onActivate(o.id)}>
                <span class="sm-power-icon" data-pulse=${pulsing ? '1' : '0'}>
                  <svg viewBox="0 0 24 24" width="26" height="26" fill="none"
                       stroke="currentColor" stroke-width="2" stroke-linecap="round">
                    <path d=${ICONS[o.id] || ICONS.restart} />
                  </svg>
                </span>
                <span class="sm-power-text">
                  <b>${isScan ? (scanning ? o.busy : o.label)
                        : pending ? o.busy
                        : confirmId === o.id ? `Confirm ${o.label}?`
                        : o.label}</b>
                  <i data-result=${isScan && scanResult ? '1' : '0'}>
                    ${isScan && scanResult ? scanResult : o.desc}
                  </i>
                </span>
              </div>`
          })}

          <button class="sm-power-cancel" onClick=${onCancel} disabled=${busy}>Cancel</button>

          <div class="sm-hint sm-hint-modal">
            ${busy ? ' ' : '↑↓ Navigate · ✕ Select · ○ Cancel'}
          </div>
        </div>
      </div>`
  }
}
