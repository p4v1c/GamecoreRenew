/**
 * The power menu — the three ways a session ends.
 *
 * Shutdown, Restart, Return to desktop, on paper, over whatever was on screen.
 * It used to wear the drawer's near-black, which was right while it opened
 * over a dark settings menu and became the only surface on this box that did
 * not match once that menu became the capture's paper screen.
 *
 * It also used to carry "Scan mapping" and "Forget mapping". Those are not
 * ways to end a session; they were here because this modal had the two-press
 * confirmation and no settings screen did. They now live in
 * Settings → Controllers, with the confirmation, and index.js declares
 * `powerOmit: ['scan', 'forget']` so the host stops sending them. The host
 * refuses to drop restart, shutdown or desktop whatever a theme asks, so no
 * theme can build a box that cannot be turned off.
 *
 * Markup only. The two-press confirmation, the pending lock that keeps every
 * close path inert while a command is in flight, and the failsafe that gives
 * the screen back when the OS never actually powers off all stay in
 * PowerModal — a view that could reimplement those could also get shutdown
 * wrong, and this is the screen where that costs the most.
 *
 * Rendered in the order the host hands them over, never reordered here:
 * `focusIdx` is an index into that array, so a view that rearranged its rows
 * would send the cursor jumping up the screen on a press of down.
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

// The ids that end a session. Used only to place one heading, and only when
// something precedes it — a theme that omits the mapping utilities gets three
// session rows and no heading, because a heading over the entire list labels
// nothing.
const SESSION = new Set(['restart', 'shutdown', 'desktop'])

export const createPowerView = (sdk) => {
  const { html, React } = sdk.ui
  const Fragment = React.Fragment

  return ({ options, focusIdx, confirmId, pendingId, scanning, scanResult, onActivate, onCancel }) => {
    const busy = pendingId !== null
    const headAt = options.findIndex((o) => SESSION.has(o.id))

    return html`
      <div class="cz-pwr-scrim" onClick=${(e) => { if (e.target === e.currentTarget && !busy) onCancel() }}>
        <div class="cz-pwr">
          <div class="cz-pwr-title">System</div>

          ${options.map((o, i) => {
            const pending = pendingId === o.id
            const isScan = o.id === 'scan'
            const pulsing = pending || (isScan && scanning)
            return html`
              <${Fragment} key=${o.id}>
                ${i === headAt && headAt > 0
                  ? html`<div class="cz-pwr-head">Ending the session</div>` : null}
                <div class="cz-pwr-row"
                     data-on=${i === focusIdx ? '1' : '0'}
                     data-confirm=${confirmId === o.id ? '1' : '0'}
                     data-dim=${busy && !pending ? '1' : '0'}
                     style=${{ '--row-accent': o.color }}
                     onClick=${() => onActivate(o.id)}>
                  <span class="cz-pwr-icon" data-pulse=${pulsing ? '1' : '0'}>
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="none"
                         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d=${ICONS[o.id] || ICONS.restart} />
                    </svg>
                  </span>
                  <span class="cz-pwr-text">
                    <b>${isScan ? (scanning ? o.busy : o.label)
                          : pending ? o.busy
                          : confirmId === o.id ? `Press again to ${o.label.toLowerCase()}`
                          : o.label}</b>
                    <i>${isScan && scanResult ? scanResult : o.desc}</i>
                  </span>
                </div>
              <//>`
          })}

          <button class="cz-pwr-cancel" onClick=${onCancel} disabled=${busy}>Cancel</button>
          <div class="cz-pwr-hint">${busy ? ' ' : '↑↓ Move · ✕ Select · ○ Cancel'}</div>
        </div>
      </div>`
  }
}
