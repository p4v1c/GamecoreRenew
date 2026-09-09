/** The controller screen, in the mockup's control-center frame.
 *
 * Every prop here is the host's, the live pad diagram included: `Art` arrives
 * ready-made and already bound to the input bus, so this file draws the panel
 * around it and nothing else. `onRemap` and the hold gesture are load-bearing
 * — for a pad SDL cannot name, the mapping wizard is the only way to make the
 * box usable at all, and a shipped theme that dropped it is what
 * backend/tests/test_shipped_theme_views.py exists to catch.
 */
export function createController(sdk) {
  const {html} = sdk.ui
  return function Controller({name, layoutLabel, connected, notice, controllers,
                              usbDevices = [], glyphs, mappings, onClose, onRemap, Art}) {
    return html`<${sdk.defaults.SettingsOverlay} onClose=${onClose} width=${980}>
      <section className="control-center controller-dialog">
        <div className="center-top">
          <div><span className="eyebrow">ACCESSORIES / CONTROLLERS</span><h2>${name}</h2></div>
          <span className="sample-badge">${connected ? 'CONNECTED' : 'NO CONTROLLER'}</span>
          <button className="close-dialog icon-button" onClick=${onClose}
                  aria-label="Close controllers">×</button>
        </div>
        ${notice ? html`<p className="mock-footnote">${notice}</p>` : null}
        <div className="controller-body">
          <div className="controller-art"><${Art} /></div>
          <div className="controller-side">
            <p className="eyebrow">${layoutLabel}</p>
            <p>${connected ? 'Connected · live input display'
              : 'Connect a controller to test its inputs.'}</p>
            ${controllers.map((c, i) => html`<div className="device-row" key=${i}>
              <span><strong>${c.label || c.name || 'Controller'}</strong>
                <small>${c.player != null ? `Player ${c.player}` : 'Connected'}${
                  Number.isFinite(c.level) && c.level >= 0
                    ? ` · ${c.level}%${c.charging ? ' · charging' : ''}` : ''}</small></span>
            </div>`)}
            ${usbDevices.length ? html`<div><h4>Peripherals</h4>
              ${usbDevices.map((d, i) => html`<div className="device-row" key=${i}>
                <span><strong>${d.label || d.name || 'USB device'}</strong>
                  <small>${d.status === 'present' ? 'Connected' : 'Disconnected'}</small></span>
              </div>`)}</div>` : null}
          </div>
        </div>
        <div className="controller-mappings">
          ${mappings.map(([button, action]) => html`<div key=${button}>
            <kbd>${button}</kbd><span>${action}</span></div>`)}
        </div>
        ${onRemap ? html`<button className="secondary-button" onClick=${onRemap}>
          Map this controller · Hold ${glyphs.top}</button>` : null}
        <p className="mock-footnote">Press any button to test · ${glyphs.left} ×2 to close
          · L2 manages a suspended game or application.</p>
      </section>
    <//>`
  }
}
