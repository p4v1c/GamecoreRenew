/**
 * Settings → Themes, in this theme's own hand.
 *
 * The host ships one, drawn for the dark default UI. Dressing every screen and
 * then handing over a foreign panel to change themes with is the one seam a
 * complete theme should not leave.
 *
 * Selecting still goes through the host: `sdk.themes.select` clears safe mode,
 * resets the crash count and reloads the frontend. This file only decides what
 * the picker looks like.
 */
export const createThemesPage = (sdk) => {
  const { html, useState, useEffect } = sdk.ui

  return ({ onClose, onBack }) => {
    const [items, setItems] = useState([])
    const [active, setActive] = useState(null)
    // Resolved once, on load: what you are using leads, everything else keeps
    // its order. A list that reshuffles under the cursor is unusable with a
    // d-pad.
    const [order, setOrder] = useState([])
    const [focus, setFocus] = useState(0)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')

    useEffect(() => {
      sdk.themes.list()
        .then((i) => {
          setItems(i.themes || [])
          setActive(i.active ?? null)
          const ids = [null, ...(i.themes || []).map((t) => t.id)]
          setOrder(ids.slice().sort((a, b) => (a === i.active ? -1 : b === i.active ? 1 : 0)))
          setFocus(0)
        })
        .catch(() => setError('Could not read the theme list.'))
    }, [])

    const rowFor = (id) => (id === null
      ? { id: null, name: 'Default', sub: 'The built-in GameCore look', ok: true }
      : (() => {
          const t = items.find((x) => x.id === id)
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
      // Re-applying what is already on screen tears the frontend down and
      // rebuilds it identically — a long blink that reads as a crash.
      if (r.id === active) { sdk.system.playSound('move'); return }
      setBusy(true); setError('')
      sdk.system.playSound('confirm')
      try { await sdk.themes.select(r.id) } catch { setError('Could not apply that theme.'); setBusy(false) }
    }

    useEffect(() => {
      if (!rows.length) return
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move'); setFocus((f) => (f - 1 + rows.length) % rows.length)
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move'); setFocus((f) => (f + 1) % rows.length)
        }),
        sdk.input.onGp('gp:confirm', () => setFocus((f) => { apply(f); return f })),
        sdk.input.onGp('gp:back', onBack),
      ]
      return () => offs.forEach((off) => off())
    }, [rows.length, rows.map((r) => r.id).join(), active, busy, onBack])

    return html`
      <div class="cz-scrim" data-enter="1" onClick=${(e) => e.target === e.currentTarget && onClose()}>
        <div class="cz-panel">
          <div class="cz-panel-title">
            <button class="cz-panel-back" onClick=${onBack}>‹</button> Themes
          </div>

          ${rows.map((r, i) => html`
            <div key=${r.id ?? '_default'} class="cz-row"
                 data-on=${focus === i ? '1' : '0'}
                 data-off=${r.ok ? '0' : '1'}
                 data-current=${r.id === active ? '1' : '0'}
                 onClick=${() => apply(i)}>
              <!-- Filled for the one in use, hollow for the rest: a shape
                   before it is a colour, so it survives a washed-out set. -->
              <span class="cz-theme-dot" />
              <span class="cz-row-text"><b>${r.name}</b><i>${r.sub}</i></span>
              ${r.id === active ? html`<span class="cz-theme-tag">IN USE</span>` : null}
            </div>`)}

          ${!rows.length && !error ? html`<div class="cz-note">Reading the theme list…</div>` : null}
          ${error ? html`<div class="cz-note">${error}</div>` : null}

          <div class="cz-hint cz-hint-modal">
            ↑↓ Move · ✕ Apply · ○ Back<br />
            Hold L1 + R1 for two seconds anywhere to force the default theme
          </div>
        </div>
      </div>`
  }
}
