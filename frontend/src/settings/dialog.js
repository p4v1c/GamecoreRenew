/**
 * The settings dialog (details, confirmations, password), one component so
 * the three safety rules are written once:
 *
 *   · it traps the pad: the list, rail and L1/R1 read `useDialogOpen()`;
 *   · the press that opened it cannot answer it: confirm is ignored for
 *     ARM_MS (a held Enter auto-repeats); directions are not;
 *   · focus returns to the element that had it, on the row it came from.
 *
 * `ownsInput` hands the pad to children (the on-screen keyboard); the dialog
 * still counts as open. No colour: `gcs-*` classes.
 */
const ARM_MS = 350

export const createDialogs = (sdk) => {
  const { html, useState, useEffect, useRef } = sdk.ui

  // How many dialogs this screen has up. Module state rather than a context:
  // the pages are built by factories, not rendered under a provider, and the
  // count is the only thing anyone needs to know.
  let depth = 0
  const listeners = new Set()
  const bump = (d) => {
    depth = Math.max(0, depth + d)
    listeners.forEach((fn) => fn(depth))
  }

  /** True while any dialog on this screen is open. */
  const useDialogOpen = () => {
    const [n, setN] = useState(depth)
    useEffect(() => {
      listeners.add(setN)
      setN(depth)
      return () => { listeners.delete(setN) }
    }, [])
    return n > 0
  }

  let seq = 0

  /**
   * @param actions   [{ id, label, desc?, primary?, danger?, disabled?, run }]
   * @param initial   which action has the cursor first — the SAFE one for a
   *                  confirmation, so a stray press cancels rather than destroys
   * @param onCancel  ○, a click on the scrim, Escape
   */
  const Dialog = ({ kicker, title, body, children, actions = [], initial = 0,
                    onCancel, ownsInput = false, wide = false }) => {
    const [idx, setIdx] = useState(Math.max(0, Math.min(initial, actions.length - 1)))
    const openedAt = useRef(Date.now())
    const idRef = useRef(`gcs-dlg-${++seq}`)
    const btnRefs = useRef([])
    const rootRef = useRef(null)

    const ref = useRef({ idx, actions, onCancel })
    useEffect(() => { ref.current = { idx, actions, onCancel } })

    useEffect(() => {
      bump(1)
      const before = typeof document !== 'undefined' ? document.activeElement : null
      return () => {
        bump(-1)
        // Only if nothing else has claimed focus since, and only an element
        // still in the page: a list refresh may have replaced it.
        if (before && before.isConnected && typeof before.focus === 'function') {
          try { before.focus({ preventScroll: true }) } catch { /* detached */ }
        }
      }
    }, [])

    // The pad's cursor and the DOM's focus are one thing, so Tab, a mouse and
    // the pad can take turns without the highlight and the real focus parting.
    useEffect(() => {
      if (ownsInput) return
      const el = btnRefs.current[idx]
      if (el && typeof el.focus === 'function') el.focus({ preventScroll: true })
    }, [idx, ownsInput])

    // A list that shrinks under the cursor (a busy action disappearing) must
    // not strand it past the end.
    useEffect(() => {
      if (idx >= actions.length) setIdx(Math.max(0, actions.length - 1))
    }, [actions.length, idx])

    const run = (a) => {
      if (!a || a.disabled) return
      sdk.system.playSound('confirm')
      a.run()
    }

    useEffect(() => {
      if (ownsInput) return
      const len = () => Math.max(1, ref.current.actions.length)
      const move = (d) => { sdk.system.playSound('move'); setIdx((i) => (i + d + len()) % len()) }
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => move(-1)),
        sdk.input.onGp('gp:dpad-left', () => move(-1)),
        sdk.input.onGp('gp:dpad-down', () => move(1)),
        sdk.input.onGp('gp:dpad-right', () => move(1)),
        sdk.input.onGp('gp:confirm', () => {
          if (Date.now() - openedAt.current < ARM_MS) return
          run(ref.current.actions[ref.current.idx])
        }),
        sdk.input.onGp('gp:back', () => { sdk.system.playSound('back'); ref.current.onCancel() }),
      ]
      return () => offs.forEach((off) => off())
    }, [ownsInput])

    // Tab stays inside. Everything behind the scrim is inert for the pad, and
    // a keyboard must not be able to walk out to it either.
    const onKeyDown = (e) => {
      if (e.key !== 'Tab' || ownsInput) return
      const list = btnRefs.current.filter((b) => b && !b.disabled)
      if (!list.length) return
      const at = list.indexOf(document.activeElement)
      if (e.shiftKey && at <= 0) { e.preventDefault(); list[list.length - 1].focus() }
      else if (!e.shiftKey && at === list.length - 1) { e.preventDefault(); list[0].focus() }
    }

    const rows = actions.some((a) => a.desc)

    return html`
      <div class="gcs-set-dialog-scrim gcs-dlg-scrim"
           onClick=${(e) => { if (e.target === e.currentTarget) onCancel() }}>
        <div class=${`gcs-set-dialog gcs-dlg${wide ? ' gcs-dlg-wide' : ''}`} ref=${rootRef}
             role="dialog" aria-modal="true" aria-labelledby=${idRef.current}
             onKeyDown=${onKeyDown}>
          ${kicker ? html`<div class="gcs-set-kicker">${kicker}</div>` : null}
          <div class="gcs-set-dialog-title" id=${idRef.current}>${title}</div>
          ${body ? html`<p class="gcs-set-sub gcs-dlg-body">${body}</p>` : null}
          ${children || null}
          ${actions.length ? html`
            <div class=${rows ? 'gcs-dlg-rows' : 'gcs-dlg-actions'}>
              ${actions.map((a, i) => html`
                <button key=${a.id} type="button"
                        ref=${(el) => { btnRefs.current[i] = el }}
                        class=${rows ? 'gcs-dlg-row' : 'gcs-dlg-btn'}
                        data-on=${!ownsInput && idx === i ? '1' : '0'}
                        data-primary=${a.primary ? '1' : '0'}
                        data-danger=${a.danger ? '1' : '0'}
                        disabled=${!!a.disabled}
                        onFocus=${() => setIdx(i)}
                        onClick=${() => { setIdx(i); run(a) }}>
                  ${rows
                    ? html`<span class="gcs-row2-text"><b>${a.label}</b>${a.desc ? html`<i>${a.desc}</i>` : null}</span>
                           <span class="gcs-dlg-chev" aria-hidden="true">›</span>`
                    : a.label}
                </button>`)}
            </div>` : null}
        </div>
      </div>`
  }

  return { Dialog, useDialogOpen }
}
