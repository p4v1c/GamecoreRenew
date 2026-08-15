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
 *
 * ## The autoconfig switch
 *
 * It is HERE and not in a theme, and that is not a filing decision. This file
 * is the shared settings screen — Shelf, Summer and the built-in default all
 * draw it — so the switch exists once and every surface gets it. A switch that
 * lived in one theme would vanish when somebody changed theme while the SETTING
 * stayed in force: a box with no autoconfig and no way left to turn it back on.
 *
 * The label says what it DOES. "Autoconfig" alone means nothing to somebody
 * opening this screen for the first time, and this is a shipped feature for
 * every player, not a support tool.
 *
 * **Both directions warn first**, through the `confirm` arming in rows.js:
 * turning it off empties the controller setup GameCore wrote, turning it on
 * overwrites whatever the owner did by hand while it was off. Neither has an
 * undo. The sentence differs per direction because the losses do.
 *
 * Per-emulator exceptions are behind a row that has to be opened. They are for
 * "I configure Dolphin myself and the rest can look after itself", which is not
 * a thing to trip over on the way to the rumble toggle. With the global switch
 * off they are shown as plain readings, not switches: the global one wins, and
 * a row you can still flick while it governs nothing is a lie you can operate.
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
    // null until the backend answers. Distinct from "off": a screen that
    // assumed OFF while loading would flash a warning at everyone, and one that
    // assumed ON would hide a real one.
    const [auto, setAuto] = useState(null)
    const [showPacks, setShowPacks] = useState(false)

    useEffect(() => {
      const sync = () => setPads(readPads())
      window.addEventListener('gamepadconnected', sync)
      window.addEventListener('gamepaddisconnected', sync)
      return () => {
        window.removeEventListener('gamepadconnected', sync)
        window.removeEventListener('gamepaddisconnected', sync)
      }
    }, [])

    useEffect(() => {
      let alive = true
      sdk.api.controllers.autoconfig()
        .then((d) => { if (alive) setAuto(d) })
        .catch(() => {})
      return () => { alive = false }
    }, [])

    const autoOn = auto ? auto.enabled : true
    const packs = (auto && auto.packs) || []
    // Named, not counted. "3 exceptions" tells somebody they have a problem
    // without telling them where it is, and finding out would mean opening the
    // advanced list they may not know exists.
    const carvedOut = packs.filter((p) => !p.enabled).map((p) => p.label)

    const rows = [
      ...pads.map((p, i) => ({
        id: `pad${p.index}`, type: 'info',
        label: `Player ${i + 1}`, desc: p.id, display: 'Connected',
      })),
      {
        id: 'autoconfig', type: 'toggle', value: autoOn, confirm: true,
        danger: autoOn,
        label: 'Set up controllers automatically',
        // The direction it is about to move in, spelled out — this is the
        // sentence the row shows after the first press, and it is the only
        // warning there is. Verbatim, not folded into "Press again to …":
        // these have to name what is lost, and a warning is not the place to
        // save four words.
        confirmText: autoOn
          ? 'Press again — this clears the controller setup GameCore wrote'
          : 'Press again — this replaces the controller setup you made yourself',
        desc: autoOn
          ? 'Emulators are configured for your pads whenever one connects'
          : 'OFF — no emulator is being configured. Pads you plug in will do '
            + 'nothing until you set them up inside each emulator yourself',
        busy: busy === 'autoconfig' ? 'Applying…' : '',
      },
      // Only once the answer is in, and only when there is something to say.
      // An exceptions row on a box that has none is an invitation to go and
      // create a problem.
      ...(auto && autoOn && carvedOut.length ? [{
        id: 'carved', type: 'info', label: 'Left to you',
        desc: 'These are configured by hand — GameCore does not touch them',
        display: carvedOut.join(', '),
      }] : []),
      ...(auto ? [{
        id: 'packs', type: 'action',
        label: showPacks ? 'Hide per-emulator exceptions'
                         : 'Per-emulator exceptions',
        label2: showPacks ? 'Hide' : 'Show',
        desc: 'Take one emulator over by hand and leave the rest automatic',
      }] : []),
      ...(showPacks ? packs.map((p) => (autoOn ? {
        id: `pack:${p.id}`, type: 'toggle', value: p.enabled, confirm: true,
        label: p.label,
        confirmText: p.enabled
          ? `Press again — this clears what GameCore wrote for ${p.label}`
          : `Press again — this replaces your own ${p.label} setup`,
        desc: p.enabled ? 'Configured automatically' : 'Yours — left untouched',
        danger: p.enabled,
        busy: busy === `pack:${p.id}` ? 'Applying…' : '',
      } : {
        // Not a switch while the global one is off. It would move, save, and
        // change nothing on the box — which is precisely the "setting that
        // governs nothing" this feature must not ship.
        id: `pack:${p.id}`, type: 'info', label: p.label,
        desc: 'Everything is off — turn the switch above back on first',
        display: 'Off',
      })) : []),
      {
        id: 'rumble', type: 'toggle', value: rumble,
        label: 'Rumble', desc: 'Haptic feedback, in themes that ask for it',
      },
      {
        id: 'scan', type: 'action', label: 'Scan mapping', label2: 'Scan now',
        busy: busy === 'scan' ? 'Scanning…' : '',
        // Still works with the switch off — it only SAVES — but saying so
        // matters: what it saves is restored on connect by the very pipeline
        // that is switched off, so a green "Saved for PS4 Controller" would
        // otherwise promise something the box will not do until it is back on.
        desc: autoOn
          ? 'Saves the connected pad’s controls (3DS, DS, GBA…)'
          : 'Saves the connected pad’s controls — kept, but not applied again '
            + 'until automatic setup is back on',
      },
      {
        id: 'forget', type: 'action', label: 'Forget mapping', label2: 'Forget',
        busy: busy === 'forget' ? 'Forgetting…' : '',
        confirm: true, danger: true,
        desc: 'Deletes the connected pad’s saved controls, then scan again',
      },
    ]

    const applyAuto = (id, enabled, pack) => {
      if (busy) return
      const label = pack ? (packs.find((p) => p.id === pack) || {}).label : ''
      setBusy(id); setMsg('')
      sdk.api.controllers.setAutoconfig(enabled, pack)
        .then((d) => {
          if (d.ok === false) { setMsg(d.error || 'That did not work.'); return }
          setAuto(d)
          // What actually happened, by name. The backend answers with the
          // slots it emptied rather than a count, because "10 released" is not
          // something anybody can check and "Dolphin: GCPad1 unbound" is.
          // `who` because the same call does both scopes, and "your connected
          // controllers are being set up again" is a fair description of the
          // global switch and a wrong one for a single emulator.
          const who = label || 'GameCore'
          setMsg(enabled
            ? `${who} is setting your connected controllers up again — anything `
              + 'you configured by hand has been replaced.'
            : (d.released && d.released.length
                ? `Cleared: ${d.released.join(', ')}. Set your pads up inside `
                  + `${label ? label : 'each emulator'} now.`
                : 'Nothing was configured, so there was nothing to clear.'))
        })
        .catch(() => setMsg('Could not reach the backend.'))
        .finally(() => setBusy(''))
    }

    const onSet = (id, v) => {
      if (id === 'autoconfig') { applyAuto(id, v); return }
      if (id.startsWith('pack:')) { applyAuto(id, v, id.slice(5)); return }
      if (id !== 'rumble') return
      sdk.input.haptics.enabled = v
      setRumble(v)
      // The only way to find out whether this pad can do it at all: most
      // controllers expose no actuator, and a switch that silently governs
      // nothing is worse than no switch.
      if (v) sdk.input.rumble({ duration: 120, strong: 0.5, weak: 0.3 })
    }

    const onAct = (id) => {
      if (id === 'packs') { setShowPacks((v) => !v); return }
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

    // The state a box can sit in for weeks without noticing: autoconfig off,
    // a pad plugged in, nothing happening, no error anywhere. It is said at the
    // top of the screen rather than only on the row that carries the switch,
    // because somebody chasing a dead controller reads the heading and then
    // goes looking elsewhere.
    const warn = auto && !autoOn && pads.length
      ? `Automatic setup is off, so ${pads.length > 1 ? 'these pads are' : 'this pad is'} `
        + 'not configured in any emulator. Turn it back on below, or set them up '
        + 'inside each emulator yourself.'
      : ''

    return html`
      <${Rows} rows=${rows} active=${active} onLeave=${onLeave}
        onSet=${onSet} onAct=${onAct}
        title="Controllers"
        state=${auto && !autoOn ? 'AUTO SETUP OFF'
                : pads.length ? `${pads.length} PAD${pads.length > 1 ? 'S' : ''}` : ''}
        sub=${pads.length
          ? 'Press □ from anywhere for the live pad test, and to map a controller SDL does not recognise.'
          : 'No pad is answering. A wired pad appears as soon as it is plugged in; a Bluetooth one has to be connected from Bluetooth first.'}
        aside=${msg || warn
          ? html`<div class="gcs-wifi-msg">${msg || warn}</div>` : null} />`
  }
}
