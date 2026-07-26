/**
 * Settings → Themes, in Summer's own language.
 *
 * The host ships one of these, but it is drawn for the dark default UI. A theme
 * that dresses everything else and then hands you a foreign panel to change
 * themes with is exactly the seam this theme exists to remove.
 *
 * Selecting still goes through the host (sdk.themes.select): it clears safe
 * mode, resets the theme's crash count and reloads the frontend. This file only
 * decides what the picker looks like.
 */
export const createThemesPage = (sdk) => {
  const { html, useState, useEffect } = sdk.ui

  return ({ onClose, onBack }) => {
    const [items, setItems] = useState([])
    const [active, setActive] = useState(null)
    /**
     * Row order, resolved once per load: what you are using first, everything
     * else after, Default among them rather than pinned to the top — switching
     * back to it is the same gesture as switching to anything else.
     *
     * Not recomputed on selection: a list that reshuffles under the cursor is
     * unusable with a d-pad.
     */
    const [order, setOrder] = useState([])
    const [focus, setFocus] = useState(0)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')

    useEffect(() => {
      sdk.themes.list()
        .then(i => {
          setItems(i.themes || [])
          setActive(i.active ?? null)
          const ids = [null, ...(i.themes || []).map(t => t.id)]
          setOrder(ids.slice().sort((a, b) => (a === i.active ? -1 : b === i.active ? 1 : 0)))
          setFocus(0)   // the theme in use, now that it leads
        })
        .catch(() => setError('Could not read the theme list'))
    }, [])

    const rowFor = (id) => (id === null
      ? { id: null, name: 'Default', sub: 'The built-in GameCore look', ok: true }
      : (() => {
          const t = items.find(x => x.id === id)
          if (!t) return null
          return {
            id,
            name: t.name,
            sub: t.compatible
              ? [`v${t.version}`, t.author, t.description].filter(Boolean).join(' · ')
              : (t.warnings || []).join(' · ') || `needs SDK v${t.api}`,
            ok: t.compatible,
          }
        })())

    const rows = order.map(rowFor).filter(Boolean)

    const apply = async (i) => {
      const r = rows[i]
      if (busy || !r || !r.ok) return
      // Re-applying what is already on screen would tear the frontend down and
      // rebuild it identically — a long blink that reads as a crash.
      if (r.id === active) { sdk.system.playSound('move'); return }
      setBusy(true); setError('')
      sdk.system.playSound('confirm')
      try { await sdk.themes.select(r.id) } catch { setError('Could not apply that theme'); setBusy(false) }
    }

    useEffect(() => {
      if (!rows.length) return
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move'); setFocus(f => (f - 1 + rows.length) % rows.length)
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move'); setFocus(f => (f + 1) % rows.length)
        }),
        sdk.input.onGp('gp:confirm', () => setFocus(f => { apply(f); return f })),
        sdk.input.onGp('gp:back', onBack),
      ]
      return () => offs.forEach(off => off())
    }, [rows.length, rows.map(r => r.id).join(), active, busy, onBack])

    return html`
      <div class="sm-modal-wrap" onClick=${(e) => e.target === e.currentTarget && onClose()}>
        <div class="sm-panel">
          <div class="sm-panel-title">
            <button class="sm-panel-back" onClick=${onBack}>‹</button> THEMES
          </div>

          ${rows.map((r, i) => html`
            <div key=${r.id ?? '_default'} class="sm-row sm-theme-row"
                 data-on=${focus === i ? '1' : '0'}
                 data-off=${r.ok ? '0' : '1'}
                 data-current=${r.id === active ? '1' : '0'}
                 onClick=${() => apply(i)}>
              <!-- A filled disc for the theme in use, a hollow ring for the
                   rest: the marker is a shape before it is a colour, so it
                   still reads on a washed-out TV. -->
              <span class="sm-theme-dot" />
              <span class="sm-row-text"><b>${r.name}</b><i>${r.sub}</i></span>
              ${r.id === active ? html`<span class="sm-theme-tag">IN USE</span>` : null}
            </div>`)}

          ${!rows.length && !error ? html`
            <div class="sm-theme-empty">Reading the theme list…</div>` : null}
          ${error ? html`<div class="sm-theme-err">${error}</div>` : null}

          <div class="sm-hint sm-hint-modal">
            ↑↓ Navigate · ✕ Apply · ○ Back<br />
            Hold L1 + R1 for 2s anywhere to force the default theme
          </div>
        </div>
      </div>`
  }
}
