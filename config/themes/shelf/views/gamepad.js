/**
 * The controller screen.
 *
 * The live diagram arrives ready-made and already bound to the pad at 60fps,
 * so this file never touches that state — it frames it. Nor are there any
 * gamepad bindings here, on purpose: on this screen every press is a test and
 * must light up its counterpart and nothing else. ○ does not go back, and
 * leaving takes a double press of □, which the host owns.
 *
 * `onRemap` opens the mapping wizard, and this file did not destructure it —
 * neither did summer's. The button exists only in the fallback view, so on
 * both shipped themes the wizard was invisible; verified both ways, by setting
 * theme.json to `active: null` and watching it appear. For a controller SDL
 * cannot name that button is the only way to make the box usable, so a theme
 * leaving it out is not a style choice. The hold gesture in the hint bar is the
 * host's and works whatever a theme draws — this is the discoverable half.
 *
 * Props: frontend/src/components/modals/gamepad/types.ts
 */
const SEGMENTS = 4
const segsFor = (level) => Math.max(0, Math.min(SEGMENTS, Math.ceil((level || 0) / (100 / SEGMENTS))))

export const createGamepadView = (sdk) => {
  const { html } = sdk.ui

  return ({ name, layoutLabel, connected, controllers, glyphs, mappings, notice = '',
            onClose, onRemap, Art }) => {
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

          ${/* Above the diagram, because the diagram will look perfect: it
                reads the pad straight from the Gamepad API and knows nothing
                about whether any emulator was configured for it. Destructured
                here rather than left out — the same lesson as onRemap above. */''}
          ${notice ? html`<div class="cz-pad-notice">${notice}</div>` : null}

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

          ${onRemap ? html`
            <button class="cz-pad-remap" onClick=${onRemap}>
              <b>Buttons wrong or dead? — map this controller</b>
              <i>Hold ${glyphs.top}. About a minute, no keyboard.</i>
            </button>` : null}

          <div class="cz-hint cz-hint-modal">
            Press any button to test · Hold ${glyphs.top} to remap ·
            ${glyphs.left} ×2 to close
          </div>
        </div>
      </div>`
  }
}
