/**
 * The power menu: Shut down, Restart, Return to desktop, led by "In the
 * background" while a session is suspended. One markup; each theme dresses it
 * from its stylesheet through the `gcs-pwr-*` classes and `data-*` hooks. The host hands over the
 * rows, so no theme can build a box that cannot be turned off.
 *
 * Markup only: the two-press confirmation, the pending lock and the failsafe
 * stay in PowerModal. Rows render in the host's order — `focusIdx` indexes
 * that array.
 * Props: frontend/src/components/modals/power/types.ts
 */
import { PadHints, PadKey } from '../lib/padKey.js'
const ICONS = {
  sessions: 'M8 5.5v13l10.5-6.5z',
  restart: 'M3 12a9 9 0 1 0 3-6.7M3 4v5h5',
  shutdown: 'M12 3v9M6.3 6.3a9 9 0 1 0 11.4 0',
  desktop: 'M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M16 17l5-5-5-5M21 12H9',
}

// The ids that end a session. A rule separates them from the "In the
// background" row, the one row here that ends nothing.
const SESSION = new Set(['restart', 'shutdown', 'desktop'])

// `layout: 'row'` lays the rows side by side (Summer); the host binds ← → as
// well as ↑ ↓, so only the hint changes.
const HINTS = { column: '↑↓ Move · ✕ Select · ○ Close', row: '←→ Move · ✕ Select · ○ Close' }

export const createPowerView = (sdk, parts = {}) => {
  const { html, React } = sdk.ui
  // See screen.js: the palette rides on a class so the built-in default's
  // always-loaded stylesheet cannot repaint a theme's power menu.
  const skin = parts.skin ? ` ${parts.skin}` : ''
  const layout = parts.layout === 'row' ? 'row' : 'column'
  const Fragment = React.Fragment

  return ({ options, focusIdx, confirmId, pendingId, onActivate, onCancel }) => {
    const busy = pendingId !== null
    const headAt = options.findIndex((o) => SESSION.has(o.id))

    return html`
      <div class=${`gcs-pwr-scrim${skin}`} onClick=${(e) => { if (e.target === e.currentTarget && !busy) onCancel() }}>
        <div class="gcs-pwr" data-layout=${layout}>
          <div class="gcs-pwr-title"><span>Power</span></div>
          <div class="gcs-pwr-list">

          ${options.map((o, i) => {
            const pending = pendingId === o.id
            return html`
              <${Fragment} key=${o.id}>
                ${i === headAt && headAt > 0 ? html`<div class="gcs-pwr-sep" role="separator" />` : null}
                <div class="gcs-pwr-row" data-id=${o.id}
                     data-on=${i === focusIdx ? '1' : '0'}
                     data-confirm=${confirmId === o.id ? '1' : '0'}
                     data-dim=${busy && !pending ? '1' : '0'}
                     style=${{ '--row-accent': o.color }}
                     onClick=${() => onActivate(o.id)}>
                  <span class="gcs-pwr-icon" data-pulse=${pending ? '1' : '0'}>
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="none"
                         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d=${ICONS[o.id] || ICONS.restart} />
                    </svg>
                  </span>
                  <span class="gcs-pwr-text">
                    <b>${pending ? o.busy : confirmId === o.id ? `${o.label}?` : o.label}</b>
                    <i>${confirmId === o.id && !pending
                      ? html`Press <${PadKey} k="✕" /> again, or <${PadKey} k="○" /> to cancel`
                      : o.desc}</i>
                  </span>
                </div>
              <//>`
          })}
          </div>

          <div class="gcs-pwr-hint">${busy ? ' ' : html`<${PadHints} text=${HINTS[layout]} />`}</div>
        </div>
      </div>`
  }
}
