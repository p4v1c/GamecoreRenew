/**
 * Settings → Controllers.
 *
 * This is the theme's own page, and the only one, because the capture asks for
 * a Controllers entry the host has no page for. What it must NOT do is invent
 * one: the capture's rows — stick dead zone, exit combination, per-pad battery
 * bars — have no setting behind them on this box. Dead zones live in each
 * emulator's generated config, the exit hotkey is written by configgen rather
 * than chosen, and the battery levels that exist cannot be tied to a pad on
 * screen (see below). A slider governing nothing is worse than no slider.
 *
 * So this page answers the two questions that CAN be answered truthfully: what
 * is plugged in right now, and where the three real controller settings are.
 * The last part is the point — rumble on the Audio page and mapping in the
 * power menu are both correct places and both impossible to guess at.
 *
 * The pad list comes from the Gamepad API, not from `sysinfo.controllers`.
 * That field is `read_batteries()`, a sysfs scan which only sees pads exposing
 * a battery: a wired pad has none, and would be reported as "not connected" by
 * the one screen whose whole job is to say whether it is. The batteries are
 * still shown — as their own list, under their own heading, unjoined. Matching
 * them to pads by name would be a guess, and a wrong guess here reads as the
 * box confusing player one with player two.
 */
export const createControllersPage = (sdk) => {
  const { html, useState, useEffect } = sdk.ui
  const { SettingsOverlay, BackBar } = sdk.defaults

  const readPads = () =>
    (navigator.getGamepads ? Array.from(navigator.getGamepads()) : [])
      .filter(Boolean)
      .map((p) => ({ index: p.index, id: p.id, buttons: p.buttons.length, axes: p.axes.length }))

  return ({ onClose, onBack }) => {
    const [pads, setPads] = useState(readPads)
    const [batteries, setBatteries] = useState([])

    useEffect(() => {
      let alive = true
      sdk.api.sysinfo()
        .then((si) => { if (alive) setBatteries(si.controllers || []) })
        .catch(() => {})
      return () => { alive = false }
    }, [])

    // A pad connected while this page is open must appear on it. Polling would
    // do, but the events exist and fire on exactly the two transitions.
    useEffect(() => {
      const sync = () => setPads(readPads())
      window.addEventListener('gamepadconnected', sync)
      window.addEventListener('gamepaddisconnected', sync)
      return () => {
        window.removeEventListener('gamepadconnected', sync)
        window.removeEventListener('gamepaddisconnected', sync)
      }
    }, [])

    // ○ leaves. The host's sub-pages get this from `useSubPageGamepad`, which
    // is internal; a theme page binds it itself or becomes a room with no door.
    useEffect(() => sdk.input.onGp('gp:back', onBack), [onBack])

    return html`
      <${SettingsOverlay} onClose=${onClose}>
        <${BackBar} label="CONTROLLERS" onBack=${onBack} />

        ${pads.length === 0
          ? html`<div class="cz-note">No pad is answering. A wired pad shows up as
                 soon as it is plugged in; a Bluetooth one has to be connected
                 from Settings → Bluetooth first.</div>`
          : pads.map((p) => html`
              <div key=${p.index} class="cz-ctl-row">
                <span class="cz-ctl-slot">P${p.index + 1}</span>
                <span class="cz-ctl-text">
                  <b>${p.id}</b>
                  <i>${p.buttons} buttons · ${p.axes} axes</i>
                </span>
              </div>`)}

        ${batteries.length > 0 ? html`
          <div class="cz-ctl-head">Batteries reported</div>
          ${batteries.map((b, i) => html`
            <div key=${i} class="cz-ctl-row">
              <span class="cz-ctl-slot">${b.level}%</span>
              <span class="cz-ctl-text">
                <b>${b.label || b.name || 'Controller'}</b>
                <i>${b.charging ? 'Charging' : 'On battery'}</i>
              </span>
            </div>`)}
          <div class="cz-ctl-note">
            Read from the kernel, which names the device its own way — that is
            why these are listed apart from the pads above rather than beside
            them.
          </div>` : null}

        <div class="cz-ctl-head">Where the settings are</div>
        <div class="cz-ctl-note">
          <b>Test a pad, or map one SDL does not know</b> — press □ from anywhere.<br />
          <b>Vibration</b> — Settings → Audio, with the other feedback settings.<br />
          <b>Save or forget a pad's controls</b> — the power menu, next to Restart.
        </div>

        <div class="cz-hint cz-hint-modal">○ Back</div>
      <//>`
  }
}
