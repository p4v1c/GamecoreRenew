/**
 * The power menu — markup only, and this is the surface where that matters most.
 *
 * The two-press confirmation, the pending lock that keeps every close path
 * inert while a command is in flight, the failsafe that unfreezes the UI when
 * the OS never actually powers off, and the mapping scan all stay in
 * PowerModal. A view that could reimplement those could also get shutdown
 * wrong, and getting shutdown wrong means a box that will not turn off.
 *
 * So this file draws `confirmId` and `pendingId`; it never decides them.
 */
export const createPowerView = (sdk) => {
  const { html, motion } = sdk.ui

  return ({
    options, focusIdx, confirmId, pendingId, scanning, scanResult,
    onFocus, onActivate, onCancel,
  }) => html`
    <${sdk.defaults.SettingsOverlay} onClose=${onCancel}>
      <${sdk.defaults.Label} text="POWER" />

      <div class="dr-power">
        ${options.map((o, i) => {
          const confirming = confirmId === o.id
          const busy = pendingId === o.id
          return html`
            <${motion.div} key=${o.id}
              animate=${{ scale: confirming ? 1.02 : 1 }}
              transition=${{ type: 'spring', stiffness: 400, damping: 28 }}
              class="dr-power-row"
              data-on=${focusIdx === i ? '1' : '0'}
              data-confirm=${confirming ? '1' : '0'}
              style=${{
                borderColor: confirming || focusIdx === i ? `${o.color}88` : 'rgba(255,255,255,0.07)',
                background: confirming
                  ? `${o.color}22`
                  : focusIdx === i ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.03)',
                // A command in flight must not look pressable, and must not be.
                opacity: pendingId && !busy ? 0.4 : 1,
                pointerEvents: pendingId ? 'none' : 'auto',
              }}
              onMouseEnter=${() => onFocus(i)}
              onClick=${() => onActivate(o.id)}>
              <span class="dr-power-icon" style=${{ color: o.color }}>${o.icon}</span>
              <span class="dr-power-text">
                <b style=${{ color: confirming ? o.color : '#fff' }}>
                  ${busy ? o.busy : confirming ? `${o.label} — press again` : o.label}
                </b>
                <i>${o.desc}</i>
              </span>
            <//>`
        })}
      </div>

      ${scanning ? html`<div class="dr-power-note">Scanning controller mappings…</div>` : null}
      ${scanResult ? html`<div class="dr-power-note">${scanResult}</div>` : null}

      <div class="dr-hint">
        ${pendingId ? 'Working…' : '↑↓ Select · ✕ Confirm (twice) · ○ Cancel'}
      </div>
    <//>`
}
