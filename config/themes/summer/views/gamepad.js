/**
 * The controller screen — DESIGN-BRIEF.md §3.8.
 *
 * The live diagram arrives ready-made and already bound to the pad, so this
 * file never touches the 60 fps state: it frames it. The brief's own layout —
 * eyebrow and pad name, diagram, a readout column on the right, mappings, hint
 * bar — in glass over the ocean.
 *
 * No gamepad bindings here, on purpose: on this screen every press is a test
 * and must only light up its counterpart. Leaving takes a double press of □,
 * which the host owns.
 *
 * Props: frontend/src/components/modals/gamepad/types.ts
 */
const SEGMENTS = 4
const segsFor = (level) => Math.max(0, Math.min(SEGMENTS, Math.ceil((level || 0) / (100 / SEGMENTS))))

export const createGamepadView = (sdk) => {
  const { html } = sdk.ui

  return ({ name, layoutLabel, connected, controllers, glyphs, mappings, onClose, Art }) => {
    const pad = controllers[0]
    const segs = pad ? segsFor(pad.level) : 0
    return html`
      <div class="sm-modal-wrap" onClick=${(e) => e.target === e.currentTarget && onClose()}>
        <div class="sm-panel sm-gamepad">
          <div class="sm-gamepad-head">
            <span class="sm-panel-title sm-gamepad-eyebrow">CONTROLLER</span>
            <b class="sm-gamepad-name">${name}</b>
            ${pad ? html`<span class="sm-chip sm-gamepad-player">Player ${pad.player ?? 1}</span>` : null}
          </div>

          <div class="sm-gamepad-body">
            <div class="sm-gamepad-art" data-off=${connected ? '0' : '1'}>
              <${Art} />
              ${connected ? null : html`
                <div class="sm-gamepad-empty">
                  <b>No controller detected</b>
                  <i>Pair a pad over Bluetooth or plug it in</i>
                </div>`}
            </div>

            <div class="sm-gamepad-readout">
              <span class="sm-gamepad-cap">LAYOUT</span>
              <b class="sm-gamepad-val">${layoutLabel}</b>

              <span class="sm-gamepad-cap">BATTERY</span>
              ${pad ? html`
                <div class="sm-gamepad-bat">
                  <span class="sm-bat">
                    ${Array.from({ length: SEGMENTS }, (_, k) => html`
                      <i key=${k} data-fill=${k < segs ? '1' : '0'} />`)}
                  </span>
                  <b class="sm-gamepad-pct">${pad.level}%</b>
                </div>
                ${pad.charging ? html`<span class="sm-gamepad-charging">Charging</span>` : null}`
              : html`<b class="sm-gamepad-val sm-gamepad-na">Battery n/a</b>`}
            </div>
          </div>

          <div class="sm-gamepad-maps">
            ${mappings.map(([key, action]) => html`
              <div key=${key} class="sm-gamepad-map">
                <kbd>${key}</kbd><span>${action}</span>
              </div>`)}
          </div>

          <div class="sm-hint sm-hint-modal">
            Press any button to test · ${glyphs.left} ×2 Close
          </div>
        </div>
      </div>`
  }
}
