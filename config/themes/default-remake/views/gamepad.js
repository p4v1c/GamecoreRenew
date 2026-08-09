/**
 * The controller screen — markup around a diagram the host draws.
 *
 * `Art` is 300+ lines of SVG already wired to the 60 fps pad state, with a
 * layout per controller family. Mount it with no props. A theme redrawing it
 * would be reimplementing the one thing this screen exists for, and would get
 * the family detection wrong the first time somebody plugs in an Xbox pad.
 *
 * `glyphs` is used everywhere a button is named. Hardcoding ✕/○/△/□ here would
 * label an Xbox pad with PlayStation faces — which is precisely the screen
 * where that is least forgivable, because it is the screen someone opens when
 * their controller is not behaving.
 *
 * `onRemap` is drawn because a pad SDL cannot name is unusable until it is
 * mapped, and this is the only route to the wizard that does not require
 * navigating a settings tree with the controller that does not work yet.
 */
export const createGamepadView = (sdk) => {
  const { html } = sdk.ui

  return ({
    name, layoutLabel, connected, controllers, usbDevices,
    glyphs, mappings, onClose, onRemap, Art, Battery,
  }) => html`
    <${sdk.defaults.SettingsOverlay} onClose=${onClose}>
      <${sdk.defaults.Label} text="CONTROLLER" />

      <div class="dr-pad-head">
        <div class="dr-pad-name">
          <b data-on=${connected ? '1' : '0'}>${name}</b>
          <i>${layoutLabel}</i>
        </div>
        <div class="dr-pad-batts">
          ${controllers.map(c => html`
            <${Battery} key=${c.player ?? c.label}
                        player=${c.player} level=${c.battery ?? 0} charging=${c.charging} />`)}
        </div>
      </div>

      <div class="dr-pad-art"><${Art} /></div>

      ${usbDevices?.length ? html`
        <div class="dr-usb">
          <div class="dr-usb-label">ALSO CONNECTED</div>
          ${/* Deliberately separate from `controllers`: a light gun is not
                player 2, and giving one a slot is how an emulator ends up
                writing pad bindings for a device with no buttons. */
            usbDevices.map(d => html`
              <div key=${d.id ?? d.label} class="dr-usb-row">
                <span>${d.label ?? d.name}</span>
                <span data-on=${d.present ? '1' : '0'}>${d.present ? 'plugged in' : 'not detected'}</span>
              </div>`)}
        </div>` : null}

      <div class="dr-maps">
        ${mappings.map(([key, action]) => html`
          <div key=${key} class="dr-map"><b>${key}</b><i>${action}</i></div>`)}
      </div>

      ${onRemap
        ? html`<button class="dr-btn dr-remap" onClick=${onRemap}>Map this controller…</button>`
        : null}

      <div class="dr-hint">
        Press any button to test it · ${glyphs.left}${glyphs.left} to close
      </div>
    <//>`
}
