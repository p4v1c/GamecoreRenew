/**
 * Settings → Profiles: who plays on this box.
 *
 * Two levels: the list (profileCards.js: a card per profile with Switch and
 * Edit, "Add profile", then "Log in automatically"), and one profile's page
 * over the whole screen (profileDetail.js: picture, colour and theme in view,
 * Switch, Rename, Delete). ○ on a profile goes back to the list. Names come
 * from the host's on-screen keyboard.
 *
 * A box whose only profile has no name has no profiles yet: the list is one
 * row that names it, and only then can others be added.
 */
import { asList } from './list.js'
import { initial } from './avatars.js'
import { createProfileCards } from './profileCards.js'
import { createProfileDetail } from './profileDetail.js'
import { useThemeNames } from './themeNames.js'

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
  const Cards = createProfileCards(sdk)
  const Detail = createProfileDetail(sdk)

  return ({ active, onLeave, onLeft }) => {
    const [state, setState] = useState(null)
    const [editing, setEditing] = useState(null)   // a profile id, or null for the list
    const [naming, setNaming] = useState(null)     // 'new' or a profile id
    const [looks, setLooks] = useState([])
    const [stats, setStats] = useState(null)
    const [msg, setMsg] = useState('')
    const themeName = useThemeNames(sdk)

    const load = () => sdk.api.profiles.list().then(setState)
      .catch(() => setMsg('Could not read the profiles.'))
    useEffect(() => { load() }, [])
    // The themes a profile can wear: the built-in look, then each one that loads.
    useEffect(() => {
      sdk.themes.list()
        .then((i) => setLooks([{ id: null, name: 'Default', preview: null },
          ...asList(i && i.themes).filter((t) => t.compatible).map((t) => ({
            id: t.id, name: t.name,
            preview: t.preview ? `/themes/${encodeURIComponent(t.id)}/${t.preview}` : null,
          }))]))
        .catch(() => {})
    }, [])

    const list = asList(state && state.profiles)
    const palette = asList(state && state.palette)
    const unnamed = list.length === 1 && !list[0].name ? list[0] : null
    const current = list.find((p) => p.id === editing) || null
    const playing = !!current && !!state && current.id === state.active

    // Playtime is kept for the profile playing; another profile's is not read.
    useEffect(() => {
      setStats(null)
      if (!playing) return
      sdk.api.playtime.all()
        .then((rows) => setStats({
          secs: asList(rows).reduce((n, r) => n + (r.total_secs || 0), 0),
          games: asList(rows).length,
        }))
        .catch(() => {})
    }, [playing, editing])

    // Every write answers with the sentence to show; the list is re-read after.
    const run = (promise, done) => promise
      .then((r) => { setMsg(done(r)); return load() })
      .catch((e) => setMsg(String((e && e.message) || 'Could not save that.')))

    const switchTo = (id) => run(sdk.api.profiles.setActive(id), (p) => `Playing as ${p.name}.`)
    const edit = (id) => { setEditing(id); setMsg('') }
    const back = () => { setEditing(null); setMsg('') }

    const onPick = (fields) => {
      if (!current) return
      const theme = 'theme' in fields ? looks.find((t) => t.id === fields.theme) : null
      run(sdk.api.profiles.update(current.id, fields),
        () => (theme && !playing ? `${current.name} plays in ${theme.name}.` : ''))
    }

    const onDelete = () => {
      const name = current.name
      setEditing(null)
      run(sdk.api.profiles.remove(current.id), () => `${name} deleted.`)
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

    const setAuto = (on) => run(sdk.api.profiles.setAutoLogin(on),
      (r) => (r.auto_login ? 'Logs in automatically.' : 'Asks who is playing at start.'))

    const named = naming && naming !== 'new' ? list.find((p) => p.id === naming) : null
    const dialogTitle = !named ? 'New profile' : named.name ? `Rename ${named.name}` : 'First profile'
    const sub = `Who plays on this box. ${savesLine(state && state.separate_saves, state && state.shared_saves)}`
    const activeName = (list.find((p) => p.id === (state && state.active)) || {}).name

    const listView = !state ? html`<${Rows} rows=${[]} active=${false} onLeave=${onLeave} onLeft=${onLeft}
        onSet=${() => {}} onAct=${() => {}} title="Profiles" />`
      : unnamed ? html`
        <${Rows} key="setup" active=${active && !naming} onLeave=${onLeave} onLeft=${onLeft}
          rows=${[{
            id: 'start', type: 'action', label: 'Set up profiles',
            desc: 'Name the first profile. It keeps the saves already on this console.', label2: 'Start',
          }]}
          onSet=${() => {}} onAct=${() => setNaming(unnamed.id)}
          title="Profiles" state="No profiles" sub=${sub}
          aside=${msg ? html`<div class="gcs-wifi-msg">${msg}</div>` : null} />`
      : html`
        <${Cards} list=${list} activeId=${state.active} themeName=${themeName}
          active=${active && !naming && !current} onLeave=${onLeave} onLeft=${onLeft}
          title="Profiles" state=${list.length === 1 ? '1 profile' : `${list.length} profiles`} sub=${sub}
          msg=${current ? '' : msg}
          autoLogin=${!!state.auto_login}
          autoDesc=${state.auto_login
            ? `Starts as ${activeName || 'the last profile'}, without asking.`
            : 'Off: the console asks who is using the controller when it starts.'}
          onSelect=${switchTo} onEdit=${edit} onAdd=${() => setNaming('new')} onAutoLogin=${setAuto} />`

    return html`
      <${React.Fragment}>
      ${listView}

      ${current ? html`
        <${Detail} key=${current.id} profile=${current} playing=${playing} palette=${palette}
          looks=${looks} stats=${stats} msg=${msg} active=${active && !naming}
          onPick=${onPick} onSwitch=${() => switchTo(current.id)} onRename=${() => setNaming(current.id)}
          onDelete=${onDelete} onBack=${back} />` : null}

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
