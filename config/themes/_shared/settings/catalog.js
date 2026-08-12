/**
 * Settings → Emulators & apps.
 *
 * The capture's accordion: one group per hardware maker, the open one filled
 * teal with its installed-of-total count, and a two-column grid of systems
 * inside it. Grouping comes from the pack's own `family` field, and a pack that
 * does not declare one lands under "Other" — honest, where inferring a maker
 * from the id would be wrong the first time somebody ships a machine nobody
 * anticipated.
 *
 * Installing and removing stay in the host's router, which runs
 * `gamecore-emu` through the one narrow sudoers rule and streams its output
 * over the WebSocket. This file starts the job and listens for `catalog:done`;
 * it does not know how a Flatpak is installed and must not learn.
 *
 * ## Where this departs from the capture, and why
 *
 * · **No version under the emulator name.** `GET /catalog` answers with what a
 *   pack IS, not what is on disk. A version exists for Flatpak packs
 *   (`pergame.emulator_version()`) but no endpoint exposes it and it is blank
 *   for anything installed from a GitHub asset — so the row would be right for
 *   some systems and empty for others, which reads as those being broken.
 * · **No "Update" button and no "Update all".** `gamecore-emu` has `install`,
 *   `remove`, `reconfigure` and `verify` — there is no `update` verb, and
 *   nothing asks a remote what version it offers. This is the most tempting
 *   row on the screen and the most dishonest: it promises work nobody can
 *   perform. The capture's "4 updates" in the rail is the same fiction, so the
 *   rail counts what is installed instead.
 *
 * Focus runs in reading order — the group header, then its systems left to
 * right — rather than in two independent columns. Two columns look like two
 * lists and are not one: the grid reflows at narrower widths, and a cursor
 * that changes meaning with the viewport is worse than one that is merely
 * linear.
 */
export const createCatalogPage = (sdk) => {
  const { html, useState, useEffect, useRef, React } = sdk.ui
  const Fragment = React.Fragment

  return ({ active, onLeave }) => {
    const [packs, setPacks] = useState([])
    const [open, setOpen] = useState(null)
    const [busy, setBusy] = useState(false)
    const [working, setWorking] = useState('')
    const [msg, setMsg] = useState('')
    const [idx, setIdx] = useState(0)

    const load = () => sdk.api.catalog.list()
      .then((list) => {
        setPacks(list)
        // Open the first maker group rather than nothing: an accordion where
        // every row is shut looks like a screen that failed to load.
        setOpen((o) => o ?? (list.find((p) => p.family && p.family !== 'Applications')
          || list.find((p) => p.family) || {}).family ?? null)
      })
      .catch(() => setMsg('Could not read the catalogue.'))

    useEffect(() => {
      load()
      sdk.api.catalog.busy().then((r) => setBusy(!!r.busy)).catch(() => {})
      // The install runs past this component's lifetime, so the finish comes
      // back on the socket rather than from the call that started it.
      const off = sdk.system.onWsEvent('catalog:done', (d) => {
        setBusy(false); setWorking('')
        setMsg(d && d.success === false ? 'That did not finish — see the log.' : '')
        load()
      })
      return off
    }, [])

    // Hardware makers first, alphabetically; then the two groups that are not
    // makers. "Applications" is a kind of pack rather than a manufacturer, and
    // "Other" is where a pack that declares no family lands — putting either
    // above Nintendo reads as a sort that failed.
    const LAST = { Applications: 1, Other: 2 }
    const groups = []
    for (const p of packs) {
      const name = p.family || 'Other'
      let g = groups.find((x) => x.name === name)
      if (!g) { g = { name, systems: [] }; groups.push(g) }
      g.systems.push(p)
    }
    groups.sort((a, b) => (LAST[a.name] || 0) - (LAST[b.name] || 0)
      || a.name.localeCompare(b.name))

    // One flat list of what the cursor can land on, rebuilt from what is open.
    const entries = []
    for (const g of groups) {
      entries.push({ kind: 'group', group: g })
      if (open === g.name) for (const s of g.systems) entries.push({ kind: 'sys', pack: s })
    }

    const ref = useRef({ idx, entries })
    useEffect(() => { ref.current = { idx, entries } })

    const fire = (e) => {
      if (!e) return
      if (e.kind === 'group') { setOpen((o) => (o === e.group.name ? null : e.group.name)); setIdx(0); return }
      if (busy || working) return
      const p = e.pack
      setWorking(p.id); setBusy(true); setMsg('')
      const call = p.installed ? sdk.api.catalog.remove(p.id) : sdk.api.catalog.install(p.id)
      call.catch(() => { setBusy(false); setWorking(''); setMsg('Could not start that.') })
    }

    useEffect(() => {
      if (!active) return
      const len = () => Math.max(1, ref.current.entries.length)
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move'); setIdx((i) => (i - 1 + len()) % len())
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move'); setIdx((i) => (i + 1) % len())
        }),
        sdk.input.onGp('gp:dpad-left', onLeave),
        sdk.input.onGp('gp:confirm', () => { sdk.system.playSound('confirm'); fire(ref.current.entries[ref.current.idx]) }),
        sdk.input.onGp('gp:back', onLeave),
      ]
      return () => offs.forEach((off) => off())
    }, [active, onLeave, busy, working, entries.length])

    const installed = packs.filter((p) => p.installed).length
    let cursor = -1

    return html`
      <${Fragment}>
      <section class="gcs-set-main" data-zone=${active ? 'on' : 'off'}>
        <div class="gcs-set-h-row">
          <div class="gcs-set-h">Emulators & apps</div>
          <div class="gcs-wifi-state">${installed}/${packs.length} INSTALLED</div>
        </div>
        <p class="gcs-set-sub">
          Add a system, or take one off the shelf. Removing a system leaves its
          ROM folder and its saves untouched.
        </p>

        ${msg ? html`<div class="gcs-wifi-msg">${msg}</div>` : null}
        ${busy ? html`<div class="gcs-wifi-msg">Working — this streams to the log and can take a few minutes.</div>` : null}

        ${groups.map((g) => {
          const isOpen = open === g.name
          cursor += 1
          const gi = cursor
          const n = g.systems.filter((s) => s.installed).length
          return html`
            <${Fragment} key=${g.name}>
              <div class="gcs-grp" data-open=${isOpen ? '1' : '0'}
                   data-on=${active && idx === gi ? '1' : '0'}
                   onClick=${() => { setIdx(gi); fire({ kind: 'group', group: g }) }}>
                <span class="gcs-grp-caret">${isOpen ? '▼' : '▶'}</span>
                <span class="gcs-grp-name">${g.name}</span>
                <span class="gcs-grp-count">${n} / ${g.systems.length}</span>
              </div>
              ${isOpen ? html`
                <div class="gcs-grp-body">
                  ${g.systems.map((p) => {
                    cursor += 1
                    const si = cursor
                    return html`
                      <div key=${p.id} class="gcs-pack" data-on=${active && idx === si ? '1' : '0'}
                           onClick=${() => { setIdx(si); fire({ kind: 'sys', pack: p }) }}>
                        <span class="gcs-pack-dot" style=${{ background: p.color || '#8B8992' }}></span>
                        <span class="gcs-pack-text">
                          <b>${p.label}</b>
                          <i>${p.emulatorName || ''}</i>
                        </span>
                        <span class="gcs-pack-btn" data-on=${p.installed ? '0' : '1'}>
                          ${working === p.id ? '…' : p.installed ? 'Remove' : 'Install'}
                        </span>
                      </div>`
                  })}
                </div>` : null}
            <//>`
        })}
      </section>
      <//>`
  }
}
