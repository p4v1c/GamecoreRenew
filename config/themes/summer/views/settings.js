/**
 * The settings menu.
 *
 * Not in the design brief — the mockup predates the surface. Built here in the
 * same glass-on-ocean language so it does not look bolted on.
 *
 * The sub-pages are the host's: nobody should reimplement Wi-Fi scanning to
 * restyle a menu. They are rendered bare, because each one already *is* a
 * full-screen overlay; boxing one nests a position:fixed layer inside a flex
 * panel, which is what shattered the Wi-Fi page and painted it black. They are
 * restyled instead, through the --gc-overlay-* variables in theme.css.
 */
const MENU = [
  { id: 'wifi', icon: '📶', label: 'Wi-Fi', sub: 'Networks' },
  { id: 'audio', icon: '🔊', label: 'Audio', sub: 'Volume & output' },
  { id: 'bluetooth', icon: '◉', label: 'Bluetooth', sub: 'Devices & pairing' },
  { id: 'standby', icon: '🌙', label: 'Standby', sub: 'Screensaver & low power' },
  { id: 'catalog', icon: '🎮', label: 'Emulators & apps', sub: 'Add or remove systems' },
  // bios and storage were in the host's menu and in none of this one, so a
  // player on this theme could not reach either. See settings.pages in
  // theme.json — the host now says so out loud in Settings → Themes.
  { id: 'bios', icon: '🧩', label: 'BIOS', sub: 'Files each console needs' },
  { id: 'storage', icon: '💾', label: 'Storage', sub: 'Disks & safe eject' },
  { id: 'themes', icon: '🎨', label: 'Themes', sub: 'Change the look' },
  { id: 'update', icon: '↑', label: 'Update', sub: 'Check for updates' },
  { id: 'desktop', icon: '⎋', label: 'Desktop', sub: 'Return to system', danger: true },
]

export const createSettings = (sdk, ownPages = {}) => {
  const { html, useState, useEffect } = sdk.ui
  return ({ onClose }) => {
    const [page, setPage] = useState(null)
    const [focus, setFocus] = useState(0)
    // The theme's own pages win; everything else falls back to the host's,
    // which does the real work (Wi-Fi scanning, updates, pairing).
    const Pages = { ...sdk.defaults.DefaultSettingsPages, ...ownPages }

    useEffect(() => {
      if (page) return   // the sub-page brings its own bindings
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move'); setFocus(f => (f - 1 + MENU.length) % MENU.length)
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move'); setFocus(f => (f + 1) % MENU.length)
        }),
        sdk.input.onGp('gp:confirm', () => {
          sdk.system.playSound('confirm'); setFocus(f => { setPage(MENU[f].id); return f })
        }),
        sdk.input.onGp('gp:back', onClose),
      ]
      return () => offs.forEach(off => off())
    }, [page, onClose])

    if (page) {
      const P = Pages[page]
      return html`<${P} onClose=${onClose} onBack=${() => setPage(null)} />`
    }

    return html`
      <div class="sm-modal-wrap" onClick=${(e) => e.target === e.currentTarget && onClose()}>
        <div class="sm-panel">
          <div class="sm-panel-title">SETTINGS</div>
          ${MENU.map((it, i) => html`
            <div key=${it.id} class="sm-row" data-on=${focus === i ? '1' : '0'}
                 data-danger=${it.danger ? '1' : '0'} onClick=${() => setPage(it.id)}>
              <span class="sm-row-icon">${it.icon}</span>
              <span class="sm-row-text"><b>${it.label}</b><i>${it.sub}</i></span>
              <span class="sm-row-chevron">›</span>
            </div>`)}
          <div class="sm-hint sm-hint-modal">↑↓ Navigate · ✕ Select · ○ Close</div>
        </div>
      </div>`
  }
}
