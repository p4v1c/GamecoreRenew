/**
 * Settings → Profiles: who plays on this box.
 *
 * Two levels on the shared rows: the list (one row per profile, then "Add
 * profile"), and one profile's rows (play as, rename, colour, delete). ○ on a
 * profile goes back to the list. Names come from the host's on-screen keyboard.
 * Delete takes two presses, like the logs purge.
 */
import { asList } from './list.js'

/** The letter drawn on a profile's colour while no avatar art exists. */
export const initial = (name) => (Array.from(String(name || '').trim())[0] || '?').toUpperCase()

/** Which systems keep a save per profile, from the packs' `profileSaves`. */
export const savesLine = (systems) => {
  const list = asList(systems)
  return list.length
    ? `Separate saves per profile: ${list.join(', ')}. Other systems share one save.`
    : 'Every system shares one save between profiles.'
}

export const createProfilesPage = (sdk, Rows, Dialog) => {
  const { html, useState, useEffect, React } = sdk.ui
  const Keyboard = sdk.defaults.DefaultKeyboard

  return ({ active, onLeave, onLeft }) => {
    const [state, setState] = useState(null)
    const [editing, setEditing] = useState(null)   // a profile id, or null for the list
    const [naming, setNaming] = useState(null)     // 'new' or a profile id
    const [msg, setMsg] = useState('')

    const load = () => sdk.api.profiles.list().then(setState)
      .catch(() => setMsg('Could not read the profiles.'))
    useEffect(() => { load() }, [])

    const list = asList(state && state.profiles)
    const palette = asList(state && state.palette)
    const current = list.find((p) => p.id === editing) || null
    const badge = (p) => ({ color: p.color, text: initial(p.name) })
    // Every write answers with the sentence to show; the list is re-read after.
    const run = (promise, done) => promise
      .then((r) => { setMsg(done(r)); return load() })
      .catch((e) => setMsg(String((e && e.message) || 'Could not save that.')))

    const listRows = [
      ...list.map((p) => ({
        id: p.id, type: 'action', label: p.name, badge: badge(p),
        desc: p.id === state.active ? 'Playing now' : '',
        label2: 'Edit',
      })),
      { id: 'add', type: 'action', label: 'Add profile', desc: 'A name and a colour', label2: 'Add' },
    ]

    const colorIdx = current ? Math.max(0, palette.findIndex((c) => c.color === current.color)) : 0
    const editRows = current ? [
      {
        id: 'use', type: 'action', label: `Play as ${current.name}`, badge: badge(current),
        desc: current.id === state.active ? 'Playing now' : '',
        label2: current.id === state.active ? 'In use' : 'Switch',
      },
      { id: 'rename', type: 'action', label: 'Name', desc: current.name, label2: 'Rename' },
      {
        id: 'color', type: 'value', label: 'Colour', value: colorIdx,
        options: palette.map((c) => c.name), badge: { color: current.color, text: '' },
      },
      // The primary profile owns the saves made before profiles: never deleted.
      ...(!current.primary ? [{
        id: 'delete', type: 'action', label: 'Delete profile',
        desc: 'Only the profile. Games and saves stay on the box.',
        // Verbatim: `label2` would be lower-cased and eat the capital of the name.
        label2: `Delete ${current.name}`, confirmText: `Press again to delete ${current.name}`,
        danger: true, confirm: true,
      }] : []),
    ] : []

    const onAct = (id) => {
      if (!current) {
        if (id === 'add') setNaming('new')
        else { setEditing(id); setMsg('') }
        return
      }
      if (id === 'use' && current.id !== state.active) {
        run(sdk.api.profiles.setActive(current.id), (p) => `Playing as ${p.name}.`)
      } else if (id === 'rename') {
        setNaming(current.id)
      } else if (id === 'delete') {
        const name = current.name
        setEditing(null)
        run(sdk.api.profiles.remove(current.id), () => `${name} deleted.`)
      }
    }

    const onSet = (id, v) => {
      if (id !== 'color' || !current || !palette[v]) return
      run(sdk.api.profiles.update(current.id, { color: palette[v].color }), () => '')
    }

    const onName = (raw) => {
      const target = naming
      setNaming(null)
      if (target === 'new') {
        run(sdk.api.profiles.create({ name: raw }), (p) => `${p.name} added.`)
      } else {
        run(sdk.api.profiles.update(target, { name: raw }), (p) => `Renamed to ${p.name}.`)
      }
    }

    const back = () => { setEditing(null); setMsg('') }
    const named = naming && naming !== 'new' ? list.find((p) => p.id === naming) : null

    return html`
      <${React.Fragment}>
      <${Rows} key=${current ? current.id : 'list'}
        rows=${current ? editRows : state ? listRows : []}
        active=${active && !naming}
        onLeave=${current ? back : onLeave} onLeft=${current ? back : onLeft}
        onSet=${onSet} onAct=${onAct}
        title=${current ? current.name : 'Profiles'}
        state=${current ? '' : list.length === 1 ? '1 profile' : `${list.length} profiles`}
        sub=${current
          ? 'Rename, recolour or delete this profile.'
          : `Who plays on this box. With two or more, the console asks who is playing when it starts. ${savesLine(state && state.separate_saves)}`}
        aside=${msg ? html`<div class="gcs-wifi-msg">${msg}</div>` : null} />

      ${naming ? html`
        <${Dialog} kicker="Profile" title=${named ? `Rename ${named.name}` : 'New profile'}
                   wide=${true} ownsInput=${true} onCancel=${() => setNaming(null)}>
          <div class="gcs-set-kb">
            <${Keyboard} title="" placeholder="Name" initialValue=${named ? named.name : ''}
              onConfirm=${onName} onCancel=${() => setNaming(null)} />
          </div>
        <//>` : null}
      <//>`
  }
}
