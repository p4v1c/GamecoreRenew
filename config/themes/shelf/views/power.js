/**
 * The power menu — restart, shutdown, leaving for the desktop, and the two
 * halves of the mapping gesture.
 *
 * Markup only. The two-press confirmation, the pending lock that keeps every
 * close path inert while a command is in flight, and the failsafe that
 * unfreezes the UI when the OS never actually powers off all stay in
 * PowerModal — a view that could reimplement those could also get shutdown
 * wrong, and this is the screen where that costs the most.
 *
 * Five rows where the capture drew three, and they are rendered in the order
 * the host hands them over rather than the order the capture arranged them in.
 * That is not deference for its own sake: `focusIdx` is an index into that
 * array, so a view that reorders its rows sends the cursor jumping up the
 * screen when the player presses down. The capture's grouping survives as a
 * heading — the two mapping utilities the host lists first, then the three
 * ways a session ends — which happens to be the array's own order, so the
 * grouping costs nothing.
 *
 * Props: frontend/src/components/modals/power/types.ts
 */
const ICONS = {
  scan: 'M4 7V5a1 1 0 0 1 1-1h2M20 7V5a1 1 0 0 0-1-1h-2M4 17v2a1 1 0 0 0 1 1h2M20 17v2a1 1 0 0 1-1 1h-2M3 12h18',
  // Drew the restart arrows before this existed, so "forget the mapping" and
  // "reboot the box" were the same picture on adjacent rows.
  forget: 'M20 6H9l-5 6 5 6h11a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1zM18 9.5l-5 5M13 9.5l5 5',
  restart: 'M3 12a9 9 0 1 0 3-6.7M3 4v5h5',
  shutdown: 'M12 3v9M6.3 6.3a9 9 0 1 0 11.4 0',
  desktop: 'M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M16 17l5-5-5-5M21 12H9',
}

// Where the "ways a session ends" group starts. Derived from the id rather
// than written as `2`, so appending another utility to the host's list moves
// the heading with it instead of cutting the group in the wrong place.
const SESSION_HEAD = 'restart'

export const createPowerView = (sdk) => {
  const { html } = sdk.ui

  return ({ options, focusIdx, confirmId, pendingId, scanning, scanResult, onActivate, onCancel }) => {
    const busy = pendingId !== null

    return html`
      <div class="cz-scrim" data-enter="1" onClick=${(e) => { if (e.target === e.currentTarget && !busy) onCancel() }}>
        <div class="cz-panel">
          <div class="cz-panel-title">System</div>

          ${options.map((o, i) => {
            const pending = pendingId === o.id
            const isScan = o.id === 'scan'
            const pulsing = pending || (isScan && scanning)
            return html`
              <${sdk.ui.React.Fragment} key=${o.id}>
                ${o.id === SESSION_HEAD ? html`<div class="cz-power-head">Ending the session</div>` : null}
                <div class="cz-power-row"
                     data-on=${i === focusIdx ? '1' : '0'}
                     data-confirm=${confirmId === o.id ? '1' : '0'}
                     data-dim=${busy && !pending ? '1' : '0'}
                     style=${{ '--row-accent': o.color }}
                     onClick=${() => onActivate(o.id)}>
                  <span class="cz-power-icon" data-pulse=${pulsing ? '1' : '0'}>
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="none"
                         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d=${ICONS[o.id] || ICONS.restart} />
                    </svg>
                  </span>
                  <span class="cz-power-text">
                    <b>${isScan ? (scanning ? o.busy : o.label)
                          : pending ? o.busy
                          : confirmId === o.id ? `Press again to ${o.label.toLowerCase()}`
                          : o.label}</b>
                    <i>${isScan && scanResult ? scanResult : o.desc}</i>
                  </span>
                </div>
              <//>`
          })}

          <button class="cz-power-cancel" onClick=${onCancel} disabled=${busy}>Cancel</button>
          <div class="cz-hint cz-hint-modal">${busy ? ' ' : '↑↓ Move · ✕ Select · ○ Cancel'}</div>
        </div>
      </div>`
  }
}
