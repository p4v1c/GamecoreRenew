/**
 * The capture's settings row, and the four controls it comes in.
 *
 * Controllers, Audio and System are the same screen with different contents:
 * one wide card, a stack of rows, each row a label, a sentence under it, and a
 * control on the right. Writing that three times would have produced three
 * subtly different rows — three focus rings, three toggle sizes, three ideas
 * of how far one press of ← moves a slider.
 *
 * The four controls, and what each is for:
 *   · toggle  — a boolean. ✕ flips it.
 *   · value   — a short list. ← and → step through it; it wraps.
 *   · slider  — a number 0–100. ← and → move it by `step`.
 *   · action  — a button. ✕ runs it.
 *
 * **Destructive rows arm before they fire.** A row marked `confirm` takes two
 * presses, and the label says so in between. That protection came from
 * PowerModal, where "Forget mapping" used to live precisely because that modal
 * had it and no settings screen did. Moving the row without moving the
 * protection would have been the whole point of the move, undone: it deletes
 * work the owner did by hand inside an emulator's own input UI, and there is
 * no undo anywhere on this box. Moving focus away disarms it, so a row cannot
 * sit primed while somebody scrolls past it.
 *
 * `confirm` applies to TOGGLES as well as actions. It was action-only while the
 * only destructive rows were buttons; the autoconfig switch is a boolean whose
 * two directions each destroy something, and a switch that wipes a controller
 * setup on one press is exactly what "arm before you fire" is for. A toggle
 * gives `label2` the sentence for the direction it is ABOUT to move in.
 *
 * Slider step is 5 by default rather than 1. A stick on a settings screen is
 * a d-pad with extra steps, and 20 presses to cross a slider is what makes a
 * console feel broken from a sofa; the value is still shown exactly, so
 * nobody is guessing.
 */
const SLIDER_STEP = 5

export const createRows = (sdk) => {
  const { html, useState, useEffect, useRef, React } = sdk.ui

  /**
   * @param rows   the row specs, rebuilt from live data by the caller
   * @param active whether this column has the cursor
   * @param onSet  (id, value) for toggle / value / slider
   * @param onAct  (id) for action rows, already past any confirmation
   */
  return ({ rows, active, onLeave, onSet, onAct, title, sub, aside, state, sections }) => {
    const [idx, setIdx] = useState(0)
    const [armed, setArmed] = useState(null)

    const ref = useRef({ idx, rows, armed })
    useEffect(() => { ref.current = { idx, rows, armed } }, [idx, rows, armed])

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
          else onLeave()
        }),
        sdk.input.onGp('gp:dpad-right', () => {
          const r = cur()
          if (r && (r.type === 'value' || r.type === 'slider')) { sdk.system.playSound('move'); step(r, +1) }
        }),
        sdk.input.onGp('gp:confirm', () => { const r = cur(); if (r) { sdk.system.playSound('confirm'); fire(r) } }),
        sdk.input.onGp('gp:back', onLeave),
      ]
      return () => offs.forEach((off) => off())
    }, [active, onLeave, rows])

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
                   data-danger=${r.danger ? '1' : '0'}
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
