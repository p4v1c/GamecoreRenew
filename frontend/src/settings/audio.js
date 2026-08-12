/**
 * Settings → Audio.
 *
 * Output and master volume are the box's (`wpctl`, through the host's router).
 * Interface sounds and their volume are the player's, kept in localStorage and
 * reached through `sdk.system.sound` — which had to gain setters for this page
 * to exist at all. It was read-only, with a comment saying setting it "stays in
 * Settings → Audio"; true while that page was always the host's, and a hole the
 * moment a theme could render its own. Replacing the page would have silently
 * deleted two controls from the console.
 *
 * ## Where this departs from the capture
 *
 * · **No background music.** Nothing on this box plays any. There is no loop to
 *   start, no file to point at, and no setting to remember — the row would be a
 *   switch wired to nothing.
 * · **Rumble is on the Controllers page**, where the capture puts it, rather
 *   than here where the host's own Audio page keeps it.
 */
import { asList } from './list.js'

export const createAudioPage = (sdk, Rows) => {
  const { html, useState, useEffect } = sdk.ui

  return ({ active, onLeave }) => {
    const [volume, setVolume] = useState(50)
    const [sinks, setSinks] = useState([])
    const [uiOn, setUiOn] = useState(() => sdk.system.sound.enabled)
    const [uiVol, setUiVol] = useState(() => Math.round(sdk.system.sound.volume * 100))
    const [msg, setMsg] = useState('')

    useEffect(() => {
      sdk.api.audio.get().then((r) => setVolume(r.volume)).catch(() => {})
      sdk.api.audio.sinks().then((r) => setSinks(asList(r))).catch(() => {})
    }, [])

    const sinkIdx = Math.max(0, sinks.findIndex((s) => s.default))

    const rows = [
      ...(sinks.length ? [{
        id: 'out', type: 'value', value: sinkIdx,
        options: sinks.map((s) => s.name),
        label: 'Output device', desc: 'Where sound is routed',
      }] : [{
        id: 'out', type: 'info', display: 'None found',
        label: 'Output device', desc: 'No sink is available',
      }]),
      { id: 'vol', type: 'slider', value: volume, label: 'Master volume', desc: '' },
      {
        id: 'uion', type: 'toggle', value: uiOn,
        label: 'Interface sounds', desc: 'Navigation ticks, select and launch chimes',
      },
      { id: 'uivol', type: 'slider', value: uiVol, label: 'Menu volume', desc: 'Navigation sounds' },
    ]

    const onSet = (id, v) => {
      if (id === 'out') {
        const s = sinks[v]
        if (!s) return
        setSinks((list) => list.map((x) => ({ ...x, default: x.id === s.id })))
        sdk.api.audio.setSink(s.id).catch(() => setMsg('Could not change the output.'))
        return
      }
      if (id === 'vol') {
        setVolume(v)
        sdk.api.audio.setVolume(v)
          .then((r) => setMsg(r && r.ok === false ? (r.error || 'Could not set the volume.') : ''))
          .catch(() => setMsg('Could not reach the backend.'))
        return
      }
      if (id === 'uion') {
        sdk.system.sound.enabled = v
        setUiOn(v)
        if (v) sdk.system.playSound('confirm')
        return
      }
      if (id === 'uivol') {
        // The SDK speaks 0–1; the 0–100 the slider shows is the storage unit
        // and stays on this side of the boundary.
        sdk.system.sound.volume = v / 100
        setUiVol(v)
        sdk.system.playSound('confirm')   // preview at the new volume
      }
    }

    return html`
      <${Rows} rows=${rows} active=${active} onLeave=${onLeave}
        onSet=${onSet} onAct=${() => {}}
        title="Audio"
        state=${sinks.find((s) => s.default) ? 'ON' : ''}
        sub="Mixing runs wherever PipeWire points it. Menu sounds are attenuated separately from game output."
        aside=${msg ? html`<div class="gcs-wifi-msg">${msg}</div>` : null} />`
  }
}
