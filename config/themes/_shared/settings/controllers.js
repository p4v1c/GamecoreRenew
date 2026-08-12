/**
 * Settings → Controllers.
 *
 * This is where the two mapping utilities now live. They were in the power
 * menu, which is not where anyone looks for them: saving a pad's controls is
 * not a way to end a session, and they were only there because that modal had
 * the two-press confirmation and no settings screen did. The confirmation came
 * with them — see `rows.js`, where an `action` row marked `confirm` arms
 * before it fires and disarms when the cursor leaves.
 *
 * `powerOmit` in index.js is the other half of the move: the host filters those
 * two ids out of the power menu for this theme, so they are in one place rather
 * than two. It refuses to drop restart, shutdown or desktop whatever a theme
 * asks, so the move cannot cost anyone the ability to turn the box off.
 *
 * ## Where this departs from the capture, and why
 *
 * · **No stick dead zone.** There is no global setting. Dead zones are written
 *   per emulator by configgen, and a slider here would either govern nothing
 *   or silently disagree with thirteen config files.
 * · **No exit combination.** The hotkey is generated, not chosen. A picker
 *   would be offering a choice the box does not have.
 * · **Player rows do not cycle "Mapped / Remap…".** Remapping a pad SDL does
 *   not know is the wizard, and the wizard lives in the controller screen the
 *   □ button opens — the shell owns whether that is up, so a settings row
 *   cannot raise it. The rows say what is connected and point at □.
 *
 * Pads come from the Gamepad API rather than `sysinfo.controllers`: that field
 * is `read_batteries()`, a sysfs scan that only sees pads exposing a battery,
 * so a wired pad would be reported as absent on the one screen whose job is to
 * say whether it is there.
 */
export const createControllersPage = (sdk, Rows) => {
  const { html, useState, useEffect } = sdk.ui

  const readPads = () =>
    (navigator.getGamepads ? Array.from(navigator.getGamepads()) : [])
      .filter(Boolean)
      .map((p) => ({ index: p.index, id: p.id }))

  return ({ active, onLeave }) => {
    const [pads, setPads] = useState(readPads)
    const [rumble, setRumble] = useState(() => sdk.input.haptics.enabled)
    const [busy, setBusy] = useState('')
    const [msg, setMsg] = useState('')

    useEffect(() => {
      const sync = () => setPads(readPads())
      window.addEventListener('gamepadconnected', sync)
      window.addEventListener('gamepaddisconnected', sync)
      return () => {
        window.removeEventListener('gamepadconnected', sync)
        window.removeEventListener('gamepaddisconnected', sync)
      }
    }, [])

    const rows = [
      ...pads.map((p, i) => ({
        id: `pad${p.index}`, type: 'info',
        label: `Player ${i + 1}`, desc: p.id, display: 'Connected',
      })),
      {
        id: 'rumble', type: 'toggle', value: rumble,
        label: 'Rumble', desc: 'Haptic feedback, in themes that ask for it',
      },
      {
        id: 'scan', type: 'action', label: 'Scan mapping', label2: 'Scan now',
        busy: busy === 'scan' ? 'Scanning…' : '',
        desc: 'Saves the connected pad’s controls (3DS, DS, GBA…)',
      },
      {
        id: 'forget', type: 'action', label: 'Forget mapping', label2: 'Forget',
        busy: busy === 'forget' ? 'Forgetting…' : '',
        confirm: true, danger: true,
        desc: 'Deletes the connected pad’s saved controls, then scan again',
      },
    ]

    const onSet = (id, v) => {
      if (id !== 'rumble') return
      sdk.input.haptics.enabled = v
      setRumble(v)
      // The only way to find out whether this pad can do it at all: most
      // controllers expose no actuator, and a switch that silently governs
      // nothing is worse than no switch.
      if (v) sdk.input.rumble({ duration: 120, strong: 0.5, weak: 0.3 })
    }

    const onAct = (id) => {
      if (busy) return
      setBusy(id); setMsg('')
      const call = id === 'scan' ? sdk.api.controllers.scanMapping()
                                 : sdk.api.controllers.forgetScan()
      call
        .then((d) => {
          if (!d.ok) { setMsg(d.error || 'That did not work.'); return }
          if (id === 'scan') {
            setMsg([
              `Saved for ${d.controller}: ${d.saved?.length ? d.saved.join(', ') : 'nothing found'}`,
              // An emulator whose config plainly describes a DIFFERENT pad is
              // refused rather than filed under this one. Silence here once let
              // a DualShock 4's config be stored as the Xbox pad's.
              d.refused?.length
                ? `— skipped (configured for another pad): ${d.refused.join(', ')}` : '',
            ].filter(Boolean).join(' '))
          } else {
            setMsg(`Forgot for ${d.controller}: ${d.forgotten?.length ? d.forgotten.join(', ') : 'nothing was saved'}`)
          }
        })
        .catch(() => setMsg('Could not reach the backend.'))
        .finally(() => setBusy(''))
    }

    return html`
      <${Rows} rows=${rows} active=${active} onLeave=${onLeave}
        onSet=${onSet} onAct=${onAct}
        title="Controllers"
        state=${pads.length ? `${pads.length} PAD${pads.length > 1 ? 'S' : ''}` : ''}
        sub=${pads.length
          ? 'Press □ from anywhere for the live pad test, and to map a controller SDL does not recognise.'
          : 'No pad is answering. A wired pad appears as soon as it is plugged in; a Bluetooth one has to be connected from Bluetooth first.'}
        aside=${msg ? html`<div class="gcs-wifi-msg">${msg}</div>` : null} />`
  }
}
