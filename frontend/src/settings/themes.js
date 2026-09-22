/**
 * Settings → Themes.
 *
 * The capture treats a theme as an ordinary settings row — name, a sentence,
 * and a button that says either "In use" or "Apply" — so this page is the
 * shared row renderer with a list built from `sdk.themes.list()`.
 *
 * Selecting stays the host's: `sdk.themes.select` clears safe mode, resets the
 * crash count and reloads the frontend. A theme picker that reimplemented that
 * could leave a box in safe mode with no way out of it.
 *
 * The row order is resolved once, on load, with the theme in use first. A list
 * that reshuffles under the cursor is unusable with a d-pad — and this list
 * reshuffles by definition, because applying changes which entry sorts first.
 *
 * An incompatible theme is listed and refused rather than hidden. "Where did
 * my theme go" has no answer on screen; "needs SDK v2" does.
 */
import { asList } from './list.js'

export const createThemesPage = (sdk, Rows) => {
  const { html, useState, useEffect, useRef } = sdk.ui

  return ({ active, onLeave }) => {
    const [items, setItems] = useState([])
    const [order, setOrder] = useState([])
    const [activeId, setActiveId] = useState(null)
    const [busy, setBusy] = useState(false)
    const [msg, setMsg] = useState('')

    useEffect(() => {
      sdk.themes.list()
        .then((i) => {
          setItems(asList(i && i.themes))
          setActiveId(i.active ?? null)
          const ids = [null, ...(i.themes || []).map((t) => t.id)]
          setOrder(ids.slice().sort((a, b) => (a === i.active ? -1 : b === i.active ? 1 : 0)))
        })
        .catch(() => setMsg('Could not read the theme list.'))
    }, [])

    const rowFor = (id) => {
      if (id === null) {
        return { id: 'theme:', label: 'Default', desc: 'The built-in GameCore look', ok: true }
      }
      const t = items.find((x) => x.id === id)
      if (!t) return null
      return {
        id: `theme:${id}`,
        label: t.name,
        desc: t.compatible
          ? [t.version && `v${t.version}`, t.description].filter(Boolean).join(' · ')
          : (t.warnings || []).join(' · ') || `needs SDK v${t.api}`,
        ok: t.compatible,
      }
    }

    const rows = order.map(rowFor).filter(Boolean).map((r) => {
      const id = r.id.slice(6) || null
      const inUse = id === activeId
      return {
        id: r.id, type: 'action', label: r.label, desc: r.desc,
        label2: inUse ? 'In use' : r.ok ? 'Apply' : 'Unavailable',
        busy: busy === r.id ? 'Applying…' : '',
      }
    })

    /**
     * How long "Applying…" may last before it is a lie.
     *
     * Selecting is meant to end by this screen ceasing to exist: the shell
     * swaps to the chosen theme and takes the settings screen with it. So the
     * page used to set `busy` and only ever clear it on a rejected promise —
     * "the frontend reloads on success, so there is no done to handle".
     *
     * That is true only when the swap happens. It does not when the chosen
     * theme fails to LOAD: the request succeeds, the box records the choice,
     * `apply()` falls back to the built-in shell — and `ThemeSurface.Shell`
     * renders that fallback bare, with no key, so nothing remounts and this
     * component is still here. The promise resolved, nothing threw, and the
     * button says "Applying…" for ever over a screen that has already given
     * up. That is what a player reports as "it applies and nothing happens".
     *
     * A theme that is going to load has swapped the shell long before this.
     */
    const APPLY_GIVES_UP_MS = 6000
    const timer = useRef(null)
    useEffect(() => () => clearTimeout(timer.current), [])

    const onAct = (rid) => {
      const id = rid.slice(6) || null
      if (id === activeId) { setMsg('That one is already in use.'); return }
      const t = id && items.find((x) => x.id === id)
      if (t && !t.compatible) { setMsg('This build cannot load that theme.'); return }
      setBusy(rid); setMsg('')

      clearTimeout(timer.current)
      timer.current = setTimeout(() => {
        setBusy(false)
        // Deliberately not "failed": the box did take the choice, and it will
        // be there at the next start. What did not happen is the swap.
        setMsg('Selected, but the front end did not switch to it — that theme '
             + 'may have failed to load. Restarting the box will use it, or '
             + 'pick another one here.')
      }, APPLY_GIVES_UP_MS)

      Promise.resolve(sdk.themes.select(id))
        .catch(() => {
          clearTimeout(timer.current)
          setBusy(false)
          setMsg('Could not apply that theme.')
        })
    }

    const current = activeId
      ? (items.find((x) => x.id === activeId) || {}).name || activeId
      : 'Default'

    return html`
      <${Rows} rows=${rows} active=${active} onLeave=${onLeave}
        onSet=${() => {}} onAct=${onAct}
        title="Themes"
        state=${String(current).toUpperCase()}
        sub="Applying one restarts the front end. Hold L1 + R1 for two seconds anywhere to force the default theme back."
        aside=${msg ? html`<div class="gcs-wifi-msg">${msg}</div>` : null} />`
  }
}
