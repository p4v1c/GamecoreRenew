/**
 * Settings → System.
 *
 * Four of the host's settings pages, on one screen, the way the capture draws
 * it: the console image and its update, standby behaviour, and the disks it
 * reads from. `theme.json` still declares `update`, `standby`, `storage` and
 * `desktop` — the declaration is about what a player can REACH, and all four
 * are reachable here (or, for `desktop`, from the power menu, which is where
 * the capture puts leaving the front end).
 *
 * ## Where this departs from the capture, and why
 *
 * · **No "Software update" row.** The capture offers to update every emulator
 *   and application. `gamecore-emu` has no `update` verb and nothing asks a
 *   remote what it offers, so the row would promise work nobody can perform.
 * · **No `pacman -Syu`.** Written up at length in the README: a NOPASSWD rule
 *   for pacman is a root shell obtainable by installing any package, and an
 *   interrupted system upgrade leaves a box with no front end, no pad and no
 *   way back from a sofa.
 * · **No kernel version.** `sysinfo` does not read one.
 * · **The internal disk is shown but cannot be ejected.** `storage.report()`
 *   deliberately lists external volumes only — an Eject button on your own root
 *   filesystem is not a feature — but its size is real and comes from
 *   `sysinfo`, so it is drawn as a bar with no button rather than left out.
 */
const SAVER_MINS = [2, 4, 6, 10, 15]
const SLEEP_MINS = [10, 16, 30, 60, 0]           // 0 = never
const label = (m) => (m === 0 ? 'Never' : m >= 60 ? `${m / 60} h` : `${m} min`)
const nearest = (list, v) => {
  let best = 0
  list.forEach((x, i) => { if (Math.abs(x - v) < Math.abs(list[best] - v)) best = i })
  return best
}

export const createSystemPage = (sdk, Rows) => {
  const { html, useState, useEffect } = sdk.ui

  return ({ active, onLeave }) => {
    const [info, setInfo] = useState(null)
    const [standby, setStandby] = useState(null)
    const [volumes, setVolumes] = useState([])
    const [update, setUpdate] = useState(null)      // null = not checked yet
    const [busy, setBusy] = useState('')
    const [msg, setMsg] = useState('')

    const loadVolumes = () => sdk.api.storage.list()
      .then((r) => setVolumes(r.volumes || [])).catch(() => {})

    useEffect(() => {
      sdk.api.sysinfo().then(setInfo).catch(() => {})
      sdk.api.standby.get().then(setStandby).catch(() => {})
      loadVolumes()
      // Whether one is already running is the backend's to know: the flag does
      // not survive leaving the page, and an update outlives that by minutes.
      sdk.api.update.status().then((r) => { if (r.running) setBusy('update') }).catch(() => {})
    }, [])

    const saverIdx = standby ? nearest(SAVER_MINS, standby.screensaver_mins) : 2
    const sleepIdx = standby ? nearest(SLEEP_MINS, standby.sleep_mins) : 1

    const rows = [
      {
        id: 'update', type: 'action',
        label: 'System update',
        desc: info
          ? `GameCore v${info.version}${update === null ? ''
              : update.update_available ? ` — v${update.latest} available`
              : ' — up to date'}`
          : 'Checking this box’s version…',
        label2: update && update.update_available ? `Install ${update.latest}` : 'Check for updates',
        busy: busy === 'update' ? 'Working…' : '',
        // Installing replaces the running front end and restarts it. That is
        // not a keypress you want to be able to make by accident.
        confirm: !!(update && update.update_available),
      },
      ...(standby ? [
        {
          id: 'sb_on', type: 'toggle', value: !!standby.enabled,
          label: 'Standby mode',
          desc: 'Slideshow, then screen off when idle. SSH and updates stay up; any button wakes the box',
        },
        {
          id: 'sb_saver', type: 'value', value: saverIdx,
          options: SAVER_MINS.map(label), label: 'Screensaver after', desc: '',
        },
        {
          id: 'sb_off', type: 'value', value: sleepIdx,
          options: SLEEP_MINS.map(label), label: 'Screen off after', desc: '',
        },
      ] : []),
    ]

    const onSet = (id, v) => {
      if (!standby) return
      const patch = id === 'sb_on' ? { enabled: v }
        : id === 'sb_saver' ? { screensaver_mins: SAVER_MINS[v] }
        : id === 'sb_off' ? { sleep_mins: SLEEP_MINS[v] } : null
      if (!patch) return
      setStandby((s) => ({ ...s, ...patch }))
      sdk.api.standby.setConfig(patch)
        .then((r) => setStandby((s) => ({ ...s, ...r })))
        .catch(() => setMsg('Could not save that.'))
    }

    const onAct = (id) => {
      if (id !== 'update' || busy) return
      if (update && update.update_available) {
        setBusy('update'); setMsg('Installing — the front end restarts when it finishes.')
        sdk.api.update.apply().catch(() => { setBusy(''); setMsg('Could not start the update.') })
        return
      }
      setBusy('update'); setMsg('')
      sdk.api.update.check()
        .then((r) => {
          setUpdate(r)
          setMsg(r.update_available ? `v${r.latest} is available.` : 'This box is up to date.')
        })
        .catch(() => setMsg('Could not reach GitHub.'))
        .finally(() => setBusy(''))
    }

    const usedPct = info && info.storage_total_gb
      ? Math.round((info.storage_used_gb / info.storage_total_gb) * 100) : 0

    // Disks are rows, not a block beside the list. A block would look right and
    // be unreachable: everything focusable on this screen is a row, so an Eject
    // button anywhere else is a button no pad can press.
    const diskRows = [
      ...(info ? [{
        id: 'disk:internal', type: 'info',
        label: 'Internal disk',
        desc: `${info.storage_used_gb} GB used of ${info.storage_total_gb} GB`,
        display: 'System', bar: usedPct,
      }] : []),
      ...volumes.map((v) => ({
        id: `disk:${v.device}`,
        type: v.mounted ? 'action' : 'info',
        label: v.label || v.name,
        desc: `${v.device} · ${v.size}${v.mounted ? ` · ${v.stable_path}` : ' · not mounted'}`,
        label2: 'Eject safely',
        display: v.mounted ? '' : 'Not mounted',
        busy: busy === v.device ? 'Ejecting…' : '',
      })),
    ]

    const allRows = [...rows, ...diskRows]
    const sections = {}
    if (diskRows.length) sections[diskRows[0].id] = 'Storage'

    const act = (id) => {
      if (!id.startsWith('disk:')) return onAct(id)
      const device = id.slice(5)
      const v = volumes.find((x) => x.device === device)
      if (!v || busy) return
      setBusy(device); setMsg('')
      sdk.api.storage.unmount(device)
        .then(() => { setMsg(`Safe to remove ${v.label || v.name}.`); loadVolumes() })
        // udisks says "target is busy" when a game is still reading the disk,
        // and that sentence is the only actionable part of the response.
        .catch((e) => setMsg(String((e && e.message) || 'Could not unmount that disk.')))
        .finally(() => setBusy(''))
    }

    return html`
      <${Rows} rows=${allRows} sections=${sections} active=${active} onLeave=${onLeave}
        onSet=${onSet} onAct=${act}
        title="System"
        state=${info ? `V${info.version}` : ''}
        sub="The console image, standby behaviour, and the disks it reads from."
        aside=${msg ? html`<div class="gcs-wifi-msg">${msg}</div>` : null} />`
  }
}
