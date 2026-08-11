/**
 * The controller screen.
 *
 * The live diagram arrives ready-made and already bound to the pad at 60fps,
 * so this file never touches that state — it frames it. Nor are there any
 * gamepad bindings here, on purpose: on this screen every press is a test and
 * must light up its counterpart and nothing else. ○ does not go back, and
 * leaving takes a double press of □, which the host owns.
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
      <div class="cz-scrim" data-enter="1" onClick=${(e) => e.target === e.currentTarget && onClose()}>
        <div class="cz-panel">
          <div class="cz-panel-title">Controller</div>

          <div class="cz-pad-head">
            <b class="cz-pad-name">${name}</b>
            ${pad ? html`<span class="cz-theme-tag">PLAYER ${pad.player ?? 1}</span>` : null}
          </div>

          <div class="cz-pad-art" data-off=${connected ? '0' : '1'}>
            <${Art} />
            ${connected ? null : html`
              <div class="cz-pad-empty">
                <b>No controller detected</b>
                <i>Pair a pad over Bluetooth, or plug one in.</i>
              </div>`}
          </div>

          <div class="cz-pad-readout">
            <span>Layout <b>${layoutLabel}</b></span>
            ${pad ? html`
              <span>
                Battery
                <span class="cz-bat">
                  ${Array.from({ length: SEGMENTS }, (_, k) => html`
                    <i key=${k} data-fill=${k < segs ? '1' : '0'} />`)}
                </span>
                <b>${pad.level}%</b>${pad.charging ? html` <b>· charging</b>` : null}
              </span>`
              : html`<span>Battery <b>n/a</b></span>`}
          </div>

          <div class="cz-pad-maps">
            ${mappings.map(([k, action]) => html`
              <div key=${k} class="cz-pad-map"><kbd>${k}</kbd><span>${action}</span></div>`)}
          </div>

          <div class="cz-hint cz-hint-modal">
            Press any button to test · ${glyphs.left} ×2 to close
          </div>
        </div>
      </div>`
  }
}
