export function createController(sdk) {
  const {html} = sdk.ui
  return function Controller({name, layoutLabel, connected, notice, controllers, usbDevices = [], glyphs, mappings, onClose, onRemap, Art}) {
    return html`<${sdk.defaults.SettingsOverlay} onClose=${onClose} width=${980}>
      <section className="orbit-controller"><div className="orbit-panel-heading"><div><span className="orbit-eyebrow">CONTROLLER INPUTS</span><h2>${name}</h2></div><button className="orbit-icon-button" onClick=${onClose} aria-label="Close controller inputs">×</button></div>
        ${notice ? html`<p className="orbit-notice">${notice}</p>` : null}
        <div className="orbit-controller-body"><div className="orbit-controller-art"><${Art} /></div><div><p className="orbit-eyebrow">${layoutLabel}</p>
          <p>${connected ? 'Connected · Live input display' : 'Connect a controller to test its inputs.'}</p>
          ${controllers.map((c, i) => html`<p key=${i}>${c.player != null ? `Player ${c.player}` : 'Controller'} · ${c.label || c.name || 'Connected'}${Number.isFinite(c.level) && c.level >= 0 ? ` · ${c.level}%${c.charging ? ' · Charging' : ''}` : ''}</p>`)}
          ${usbDevices.length ? html`<div><h3>Peripherals</h3>${usbDevices.map((device, i) => html`<p key=${i}>${device.label || device.name || 'USB device'} · ${device.status === 'present' ? 'Connected' : 'Disconnected'}</p>`)}</div>` : null}
        </div></div><div className="orbit-mappings">${mappings.map(([button, action]) => html`<div key=${button}><kbd>${button}</kbd><span>${action}</span></div>`)}</div>
        ${onRemap ? html`<button className="orbit-button" onClick=${onRemap}>Map this controller · Hold ${glyphs.top}</button>` : null}
        <p className="orbit-muted">Press any button to test · ${glyphs.left} ×2 to close · L2 manages a suspended game or application.</p>
      </section><//>`
  }
}
