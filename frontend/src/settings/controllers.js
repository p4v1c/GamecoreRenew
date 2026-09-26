/**
 * Settings → Controllers.
 *
 * Not drawn: a global stick dead zone or exit combination (both are written
 * per emulator by configgen), or a per-row "Remap" (the wizard lives on the
 * controller screen, opened with □). Pads come from the Gamepad API:
 * `sysinfo.controllers` only sees pads with a battery.
 *
 * The autoconfig switch lives HERE, in the shared screen, so it exists on
 * every surface (a theme-only switch could vanish while its setting stays on).
 * Both directions warn first (`confirm` in rows.js): off empties GameCore's
 * controller setup, on overwrites manual edits; neither has an undo.
 * Per-emulator exceptions sit behind a row; with the global switch off they
 * are shown as readings, not switches.
 */
export const createControllersPage = (sdk, Rows) => {
  const { html, useState, useEffect } = sdk.ui

  const readPads = () =>
    (navigator.getGamepads ? Array.from(navigator.getGamepads()) : [])
      .filter(Boolean)
      .map((p) => ({ index: p.index, id: p.id }))

  return ({ active, onLeave, onLeft }) => {
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
        // Four emulators have no inverse — GameCore can write their config and
        // cannot empty it. Promising a clear-out there would be warning about a
        // loss that cannot happen, on the one screen whose whole job is to stop
        // lying about what is in force.
        confirmText: p.enabled
          ? (p.releasable === false
              ? `Press again — GameCore stops configuring ${p.label}. What it `
                + 'already wrote stays as it is'
              : `Press again — this clears what GameCore wrote for ${p.label}`)
          : `Press again — this replaces your own ${p.label} setup`,
        desc: p.enabled
          ? 'Configured automatically'
          : (p.releasable === false
              ? 'Yours — GameCore no longer writes it, and left what was there'
              : 'Yours — left untouched'),
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
                // Two very different reasons for an empty list, and saying the
                // wrong one is how somebody concludes the switch did nothing.
                // The first four emulators keep their config because GameCore
                // has no way to un-write it — the switch still took effect, it
                // just has nothing to undo.
                : (pack && (packs.find((p) => p.id === pack) || {}).releasable === false
                    ? `${label} is yours now — GameCore will not write it again. `
                      + 'What it wrote before is still there, so your pad keeps '
                      + 'working until you change it inside the emulator.'
                    : 'Nothing had been configured, so there was nothing to clear.')))
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
      if (id === 'packs') setShowPacks((v) => !v)
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
      <${Rows} rows=${rows} active=${active} onLeave=${onLeave} onLeft=${onLeft}
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
