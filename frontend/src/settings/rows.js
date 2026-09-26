/**
 * The settings row, shared by Controllers, Audio and System, and its four
 * controls:
 *   · toggle  — boolean, ✕ flips it
 *   · value   — short list, ←/→ step (wraps)
 *   · slider  — 0–100, ←/→ by `step` (default 5: 20 presses is too many)
 *   · action  — button, ✕ runs it
 *
 * Rows marked `confirm` (actions AND toggles) take two presses; `label2`
 * states what the second press will do. Moving focus away disarms.
 */
import { follow } from './list.js'

const SLIDER_STEP = 5

export const createRows = (sdk) => {
  const { html, useState, useEffect, useRef, React } = sdk.ui

  /**
   * @param rows   the row specs, rebuilt from live data by the caller
   * @param active whether this column has the cursor
   * @param onSet  (id, value) for toggle / value / slider
   * @param onAct  (id) for action rows, already past any confirmation
   * @param onLeft ← on a row that has nothing to adjust. The rail layout uses
   *               it to go back to the rail; the index layout, where ← has
   *               nowhere to go, passes a no-op and leaves ○ as the way out.
   */
  return ({ rows, active, onLeave, onLeft, onSet, onAct, title, sub, aside, state, sections }) => {
    const [idx, setIdx] = useState(0)
    const [armed, setArmed] = useState(null)

    const ref = useRef({ idx, rows, armed })
    useEffect(() => { ref.current = { idx, rows, armed } }, [idx, rows, armed])

    // Keep the focused row on screen.
    //
    // `.gcs-set-main` has always been `overflow: auto`, and this component has
    // always been the only thing drawing into it that could not scroll: every
    // host settings page — Bluetooth, BIOS, Storage, Catalog — calls exactly
    // this line on its own focus change. It went unnoticed here because no page
    // built on `Rows` had ever been longer than the column, so the cursor could
    // not leave the visible area. The Controllers page can now: the autoconfig
    // switch, its exceptions row and one row per emulator take it past a
    // screenful, and the d-pad walked the highlight down into rows nobody could
    // see — pressing ✕ on a control that was not on screen.
    //
    // `block: 'nearest'` scrolls the minimum needed, so a list that already fits
    // never moves at all and the top rows do not jump under the heading.
    const rowRefs = useRef([])
    useEffect(() => {
      // `?.scrollIntoView?.()`, both optional. The element can be absent for a
      // frame after the list changes, and the METHOD can be absent too: jsdom
      // implements no layout and does not define it, so the plain call threw a
      // TypeError inside a passive effect and took down every other page built
      // on this component — Audio, Display, System, Themes — in a change that
      // was only ever about Controllers.
      if (active) follow(rowRefs.current[idx], idx === 0)
    }, [idx, active, rows.length])

    // An armed row that loses the cursor disarms. Otherwise a confirmation set
    // up minutes ago is still waiting under a single press.
    //
    // Compared against the armed row rather than fired on every `idx` change:
    // a mouse click sets the focus AND arms in one go, so clearing on any
    // change disarmed the row in the same tick it was armed — the confirmation
    // was unreachable with a pointer and only worked from a pad.
    useEffect(() => {
      const cur = rows[idx]
      if (armed && (!cur || cur.id !== armed)) setArmed(null)
    }, [idx, rows, armed])

    // A list that shrinks under the cursor must not strand it past the end.
    // `fire()` reads `rows[idx]` and simply does nothing when that is
    // undefined, so the symptom is a screen where ✕ has stopped working and
    // nothing says why. Collapsing the per-emulator exceptions is the first
    // list on this screen that can shrink at all.
    useEffect(() => {
      if (idx >= rows.length) setIdx(Math.max(0, rows.length - 1))
    }, [rows.length, idx])

    const step = (r, dir) => {
      if (r.type === 'value') {
        const n = r.options.length
        onSet(r.id, (r.value + dir + n) % n)
      } else if (r.type === 'slider') {
        const s = r.step || SLIDER_STEP
        onSet(r.id, Math.max(0, Math.min(100, r.value + dir * s)))
      }
    }

    const fire = (r) => {
      // `confirm` is not an action-row privilege any more. A toggle can destroy
      // work too: the autoconfig switch empties the controller setup GameCore
      // wrote when it goes off, and overwrites whatever the owner made by hand
      // when it comes back on. Both directions cost somebody something, and
      // there is no undo anywhere on this box.
      //
      // The caller supplies `label2` per DIRECTION, because "press again to
      // turn autoconfig off" and "…to turn it on" warn about opposite things.
      if (r.confirm && ref.current.armed !== r.id) { setArmed(r.id); return }
      setArmed(null)
      if (r.type === 'toggle') { onSet(r.id, !r.value); return }
      if (r.type !== 'action') return
      onAct(r.id)
    }

    useEffect(() => {
      if (!active) return
      const len = () => Math.max(1, ref.current.rows.length)
      const cur = () => ref.current.rows[ref.current.idx]
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move'); setIdx((i) => (i - 1 + len()) % len())
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move'); setIdx((i) => (i + 1) % len())
        }),
        sdk.input.onGp('gp:dpad-left', () => {
          const r = cur()
          if (r && (r.type === 'value' || r.type === 'slider')) { sdk.system.playSound('move'); step(r, -1) }
          else (onLeft || onLeave)()
        }),
        sdk.input.onGp('gp:dpad-right', () => {
          const r = cur()
          if (r && (r.type === 'value' || r.type === 'slider')) { sdk.system.playSound('move'); step(r, +1) }
        }),
        sdk.input.onGp('gp:confirm', () => { const r = cur(); if (r) { sdk.system.playSound('confirm'); fire(r) } }),
        sdk.input.onGp('gp:back', onLeave),
      ]
      return () => offs.forEach((off) => off())
    }, [active, onLeave, onLeft, rows])

    return html`
      <section class="gcs-set-main" data-zone=${active ? 'on' : 'off'}>
        <div class="gcs-set-h-row">
          <div class="gcs-set-h">${title}</div>
          ${state ? html`<div class="gcs-wifi-state">${state}</div>` : null}
        </div>
        ${sub ? html`<p class="gcs-set-sub">${sub}</p>` : null}
        ${aside || null}

        ${rows.length === 0
          ? html`<div class="gcs-wifi-empty">Nothing to set here yet.</div>`
          : rows.map((r, i) => {
            const head = sections && sections[r.id]
            const on = active && idx === i
            const isArmed = armed === r.id
            return html`
              <${React.Fragment} key=${r.id}>
              ${head ? html`<div class="gcs-set-kicker gcs-row2-head">${head}</div>` : null}
              <div class="gcs-row2" data-on=${on ? '1' : '0'}
                   data-type=${r.type}
                   data-danger=${r.danger ? '1' : '0'}
                   role=${r.type === 'toggle' ? 'switch'
                     : r.type === 'slider' || r.type === 'value' ? 'slider'
                     : r.type === 'info' ? undefined : 'button'}
                   aria-label=${r.label}
                   aria-checked=${r.type === 'toggle' ? String(!!r.value) : undefined}
                   aria-valuemin=${r.type === 'slider' ? 0 : undefined}
                   aria-valuemax=${r.type === 'slider' ? 100 : undefined}
                   aria-valuenow=${r.type === 'slider' ? r.value : undefined}
                   aria-valuetext=${r.type === 'value' ? r.options[r.value] : undefined}
                   ref=${(el) => { rowRefs.current[i] = el }}
                   onClick=${() => { setIdx(i); fire(r) }}>
                <span class="gcs-row2-text">
                  ${/* `confirmText` is used verbatim; `label2` is lower-cased to
                       finish the sentence "Press again to …". The verbatim form
                       exists because the lower-casing eats proper nouns — a row
                       warning about "gamecube / wii" and "gamecore" reads like a
                       typo on the one screen that has to be trusted. */''}
                  <b>${isArmed
                    ? (r.confirmText || `Press again to ${String(r.label2 || r.label).toLowerCase()}`)
                    : r.label}</b>
                  ${r.desc ? html`<i>${r.desc}</i>` : null}
                  ${/* A usage bar belongs to the row it describes, so it is
                       drawn inside it rather than in a block beside the list —
                       which is also what keeps the disk reachable with a pad:
                       everything focusable on this screen is a row. */
                    r.bar != null ? html`
                    <span class="gcs-row2-bar"><i style=${{ width: `${r.bar}%` }}
                      data-level=${r.bar > 85 ? 'alert' : r.bar > 65 ? 'warn' : 'ok'}></i></span>` : null}
                </span>

                ${r.type === 'toggle' ? html`
                  <span class="gcs-tgl" data-v=${r.value ? '1' : '0'}><i></i></span>` : null}

                ${r.type === 'value' ? html`
                  <span class="gcs-val">
                    <button class="gcs-val-arrow" onClick=${(e) => { e.stopPropagation(); setIdx(i); step(r, -1) }}>‹</button>
                    <span class="gcs-val-now">${r.options[r.value]}</span>
                    <button class="gcs-val-arrow" onClick=${(e) => { e.stopPropagation(); setIdx(i); step(r, +1) }}>›</button>
                  </span>` : null}

                ${r.type === 'slider' ? html`
                  <span class="gcs-sld">
                    <span class="gcs-sld-track"><i style=${{ width: `${r.value}%` }}></i></span>
                    <span class="gcs-sld-num">${r.value}${r.unit || '%'}</span>
                  </span>` : null}

                ${r.type === 'info' ? html`
                  <span class="gcs-row2-info">${r.display}</span>` : null}

                ${r.type === 'action' ? html`
                  <span class="gcs-act" data-danger=${r.danger ? '1' : '0'} data-armed=${isArmed ? '1' : '0'}>
                    ${r.busy ? r.busy : isArmed ? 'Confirm' : (r.label2 || 'Run')}
                  </span>` : null}
              </div>
              <//>`
          })}
      </section>`
  }
}
