/**
 * Settings → Profiles: who plays on this box.
 *
 * Two levels on the shared rows: the list (one row per profile, with Select
 * and Edit, then "Add profile"), and one profile's rows (play as, rename,
 * colour, picture, delete). ○ on a
 * profile goes back to the list. Names come from the host's on-screen keyboard.
 * Delete takes two presses, like the logs purge.
 *
 * A box whose only profile has no name has no profiles yet: the list is one
 * row that names it, and only then can others be added.
 */
import { asList } from './list.js'
import { AVATARS, avatarFace, initial } from './avatars.js'

export { initial }

/**
 * Which systems keep a save per profile, from the packs' `profileSaves`.
 * The shorter list is the one named: "every system except Xbox 360" reads
 * on a TV, thirty console names do not.
 */
export const savesLine = (separate, shared) => {
  const yes = asList(separate)
  const no = asList(shared)
  if (!yes.length) return 'Every system shares one save between profiles.'
  if (!no.length) return 'Every system keeps separate saves per profile.'
  return no.length < yes.length
    ? `Every system keeps separate saves per profile, except ${no.join(', ')}.`
    : `Separate saves per profile: ${yes.join(', ')}. Other systems share one save.`
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
    const unnamed = list.length === 1 && !list[0].name ? list[0] : null
    const current = list.find((p) => p.id === editing) || null
    const badge = (p) => ({ color: p.color, text: avatarFace(html, p) })
    // Every write answers with the sentence to show; the list is re-read after.
    const run = (promise, done) => promise
      .then((r) => { setMsg(done(r)); return load() })
      .catch((e) => setMsg(String((e && e.message) || 'Could not save that.')))

    const listRows = unnamed ? [
      {
        id: 'start', type: 'action', label: 'Set up profiles',
        desc: 'Name the first profile. It keeps the saves already on this console.',
        label2: 'Start',
      },
    ] : [
      // The profile playing has nothing to select: Edit only. Every other
      // one can be switched to from the list, without opening it first.
      ...list.map((p) => ({
        id: p.id, type: 'choice', label: p.name, badge: badge(p),
        desc: p.id === state.active ? 'Playing now' : '',
        buttons: p.id === state.active
          ? [{ id: `edit:${p.id}`, label: 'Edit' }]
          : [{ id: `select:${p.id}`, label: 'Select' }, { id: `edit:${p.id}`, label: 'Edit' }],
      })),
      { id: 'add', type: 'action', label: 'Add profile', desc: 'A name and a colour', label2: 'Add' },
      {
        id: 'autologin', type: 'toggle', value: !!(state && state.auto_login), label: 'Log in automatically',
        desc: state && state.auto_login
          ? `Starts as ${(list.find((p) => p.id === state.active) || {}).name || 'the last profile'}, without asking.`
          : 'Off: the console asks who is using the controller when it starts.',
      },
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
      {
        id: 'picture', type: 'value', label: 'Picture',
        value: Math.max(0, AVATARS.findIndex(([key]) => key === current.avatar) + 1),
        options: ['Initial', ...AVATARS.map(([, label]) => label)], badge: badge(current),
      },
      // The primary profile owns the saves made before profiles: never deleted.
      ...(!current.primary ? [{
        id: 'delete', type: 'action', label: 'Delete profile',
        // Honest about where the saves go: kept on disk, but a new profile,
        // even with the same name, starts again.
        desc: `Games stay. ${current.name}’s saves are kept on the console, but no profile opens them again.`,
        // Verbatim: `label2` would be lower-cased and eat the capital of the name.
        label2: `Delete ${current.name}`, confirmText: `Press again to delete ${current.name}`,
        danger: true, confirm: true,
      }] : []),
    ] : []

    const onAct = (id) => {
      if (!current) {
        const [verb, pid] = id.split(':')
        if (id === 'start') setNaming(unnamed.id)
        else if (id === 'add') setNaming('new')
        else if (verb === 'select') run(sdk.api.profiles.setActive(pid), (p) => `Playing as ${p.name}.`)
        else if (verb === 'edit') { setEditing(pid); setMsg('') }
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
      if (id === 'autologin') {
        run(sdk.api.profiles.setAutoLogin(v), (r) => (r.auto_login ? 'Logs in automatically.' : 'Asks who is playing at start.'))
        return
      }
      if (!current) return
      if (id === 'color' && palette[v]) {
        run(sdk.api.profiles.update(current.id, { color: palette[v].color }), () => '')
      } else if (id === 'picture') {
        const pick = v > 0 && AVATARS[v - 1] ? AVATARS[v - 1][0] : null
        run(sdk.api.profiles.update(current.id, { avatar: pick }), () => '')
      }
    }

    const onName = (raw) => {
      const target = naming
      setNaming(null)
      if (target === 'new') {
        run(sdk.api.profiles.create({ name: raw }), (p) => `${p.name} added.`)
      } else {
        const first = unnamed && unnamed.id === target
        run(sdk.api.profiles.update(target, { name: raw }),
          (p) => (first ? `${p.name} is set up. Add the others below.` : `Renamed to ${p.name}.`))
      }
    }

    const back = () => { setEditing(null); setMsg('') }
    const named = naming && naming !== 'new' ? list.find((p) => p.id === naming) : null
    const dialogTitle = !named ? 'New profile' : named.name ? `Rename ${named.name}` : 'First profile'

    return html`
      <${React.Fragment}>
      <${Rows} key=${current ? current.id : 'list'}
        rows=${current ? editRows : state ? listRows : []}
        active=${active && !naming}
        onLeave=${current ? back : onLeave} onLeft=${current ? back : onLeft}
        onSet=${onSet} onAct=${onAct}
        title=${current ? current.name : 'Profiles'}
        state=${current ? '' : unnamed ? 'No profiles' : list.length === 1 ? '1 profile' : `${list.length} profiles`}
        sub=${current
          ? 'Rename, change the colour or picture, or delete this profile.'
          : `Who plays on this box. ${savesLine(state && state.separate_saves, state && state.shared_saves)}`}
        aside=${msg ? html`<div class="gcs-wifi-msg">${msg}</div>` : null} />

      ${naming ? html`
        <${Dialog} kicker="Profile" title=${dialogTitle}
                   wide=${true} ownsInput=${true} onCancel=${() => setNaming(null)}>
          <div class="gcs-set-kb">
            <${Keyboard} title="" placeholder="Name" initialValue=${named ? named.name : ''}
              onConfirm=${onName} onCancel=${() => setNaming(null)} />
          </div>
        <//>` : null}
      <//>`
  }
}
