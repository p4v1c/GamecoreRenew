/**
 * Settings → Applications.
 *
 * Steam, Stremio, Twitch, YouTube — the four `kind: 'app'` packs, as a flat
 * list. The consoles used to be here too, folded into an accordion by hardware
 * maker, and they are the Store's Consoles tab now: a destination reached with
 * △ from the dashboard, not a page inside the settings. Settings is where a
 * player changes what the box already does; the Store is where they change what
 * it HAS, and thirty-one consoles were always the wrong shape for a rail row.
 *
 * The accordion went with them. Grouping was a way to make twenty systems fit a
 * television; four applications are not a wall, and no app pack declares a
 * `family` at all — so grouping them would have produced exactly one group
 * called "Other", which is a fold with nothing behind it. (It produced that
 * before, too, and nobody noticed: the sort here listed "Applications" ahead of
 * "Other" as though some pack declared it, and none ever has.)
 *
 * ## Where the behaviour lives
 *
 * Not here. `useCatalog` (`lib/catalog.ts`) reads the list, posts the verb,
 * holds the page until `catalog:done` and re-reads after — for this page, for
 * the applications page in the fallback modal, and for the Store. This file
 * draws, and hands the cursor to that hook. The import is a departure from this
 * directory's idiom of taking everything through `sdk`, and a deliberate one:
 * the alternative is a second copy of that sequence, and the three copies that
 * existed before had already disagreed about whether removing asks twice.
 *
 * That is the fix a player will notice here. This page removed a system on ONE
 * press of ✕ — on whatever row the cursor happened to be sitting — for as long
 * as it existed. It asks twice now, because the hook does.
 *
 * ## Where this still departs from the capture, and why
 *
 * · **No version under the name.** `GET /catalog` answers with what a pack IS,
 *   not what is on disk. A version exists for Flatpak packs
 *   (`pergame.emulator_version()`) but no endpoint exposes it and it is blank
 *   for anything installed from a GitHub asset — so the row would be right for
 *   some and empty for others, which reads as those being broken.
 * · **No "Update" button and no "Update all".** `gamecore-emu` has `install`,
 *   `remove`, `reconfigure` and `verify` — there is no `update` verb, and
 *   nothing asks a remote what version it offers. It is the most tempting row
 *   on the screen and the most dishonest: it promises work nobody can perform.
 */
import { useCatalog } from '../lib/catalog'

export const createAppsPage = (sdk) => {
  const { html, useState, useEffect, useRef, React } = sdk.ui
  const Fragment = React.Fragment

  /**
   * The square at the head of a row: the pack's own logo.
   *
   * The colour is the fallback it always was: a pack that ships no logo, or a
   * logo that fails to load, gets exactly the swatch it had before. That is a
   * component's worth of state because the failure is asynchronous — the URL
   * looks fine until the image does not arrive.
   *
   * The tile behind the logo is a constant near-white on all three surfaces and
   * does NOT take the theme. These logos are somebody else's artwork at
   * somebody else's contrast; a light chip is what an app launcher does, and it
   * is the only background that works for all of them at once.
   */
  const PackMark = ({ pack }) => {
    const [failed, setFailed] = useState(false)
    // Reset when the row is reused for another pack: `failed` is about one
    // image, and React keeps this component mounted across a re-key.
    useEffect(() => { setFailed(false) }, [pack.logo])

    if (!pack.logo || failed) {
      return html`<span class="gcs-pack-dot"
                        style=${{ background: pack.color || '#8B8992' }}></span>`
    }
    return html`
      <span class="gcs-pack-dot" data-logo="1">
        <img src=${`/${pack.logo}`} alt="" loading="lazy"
             onError=${() => setFailed(true)} />
      </span>`
  }

  return ({ active, onLeave }) => {
    const catalog = useCatalog({ kind: 'app' })
    const [idx, setIdx] = useState(0)

    const rows = catalog.rows || []

    // Read live by the bindings below: they are registered once per `active`,
    // and a handler closing over its own render decides twice from the same
    // stale cursor when a burst of d-pad presses arrives.
    const ref = useRef({ idx, rows, catalog })
    useEffect(() => { ref.current = { idx, rows, catalog } })

    // The list can come back shorter than where the cursor was.
    useEffect(() => {
      if (rows.length && idx > rows.length - 1) setIdx(rows.length - 1)
    }, [rows.length, idx])

    useEffect(() => {
      if (!active) return
      const step = (d) => {
        const n = ref.current.rows.length
        if (!n) return
        sdk.system.playSound('move')
        ref.current.catalog.disarm()      // stepping away is how you say no
        setIdx((i) => (i + d + n) % n)
      }
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => step(-1)),
        sdk.input.onGp('gp:dpad-down', () => step(1)),
        sdk.input.onGp('gp:dpad-left', onLeave),
        // No `playSound` here: the hook sounds the action it actually takes,
        // and a confirm tone fired first would play twice for one press.
        sdk.input.onGp('gp:confirm', () => {
          const row = ref.current.rows[ref.current.idx]
          if (row) ref.current.catalog.act(row)
        }),
        sdk.input.onGp('gp:back', onLeave),
      ]
      return () => offs.forEach((off) => off())
    }, [active, onLeave])

    const installed = rows.filter((p) => p.installed).length

    return html`
      <${Fragment}>
      <section class="gcs-set-main" data-zone=${active ? 'on' : 'off'}>
        <div class="gcs-set-h-row">
          <div class="gcs-set-h">Applications</div>
          <div class="gcs-wifi-state">${installed}/${rows.length} INSTALLED</div>
        </div>
        <p class="gcs-set-sub">
          Add an application, or take one off the shelf. Consoles are in the
          Store — press △ on the home screen. Removing an application leaves
          its data untouched.
        </p>

        ${catalog.loadFailed
          ? html`<div class="gcs-wifi-msg">Could not read the catalogue.</div>` : null}
        ${catalog.actionError
          ? html`<div class="gcs-wifi-msg">${catalog.actionError}</div>` : null}
        ${catalog.busy
          ? html`<div class="gcs-wifi-msg">Working — this takes a few minutes.</div>` : null}
        ${catalog.armedId
          ? html`<div class="gcs-wifi-msg">Press ✕ again to remove it · any direction cancels</div>` : null}

        <div class="gcs-grp-body">
          ${rows.map((p, i) => {
            // The armed state is carried by the WORD, not by a colour.
            // `--set-danger` is defined for the built-in skin and for Orbit and
            // for neither of the other two shipped themes, so a red that only
            // appeared on one surface would leave the other two showing
            // "Remove" twice with no sign that the first press did anything.
            const armed = catalog.armedId === p.id
            return html`
              <div key=${p.id} class="gcs-pack" data-on=${active && idx === i ? '1' : '0'}
                   data-armed=${armed ? '1' : '0'}
                   onClick=${() => { setIdx(i); catalog.act(p) }}>
                <${PackMark} pack=${p} />
                <span class="gcs-pack-text">
                  <b>${p.label}</b>
                  <i>${p.description || p.emulatorName || ''}</i>
                </span>
                <span class="gcs-pack-btn" data-on=${!p.installed && !armed ? '1' : '0'}>
                  ${catalog.workingId === p.id ? '…'
                    : armed ? 'Confirm?'
                    : p.installed ? 'Remove' : 'Install'}
                </span>
              </div>`
          })}
        </div>

        ${catalog.rows !== null && rows.length === 0 && !catalog.loadFailed
          ? html`<p class="gcs-set-sub">No application packs are installed on this box.</p>`
          : null}
      </section>
      <//>`
  }
}
