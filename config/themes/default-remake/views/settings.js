/**
 * The settings menu.
 *
 * The sub-pages are the host's — nobody should reimplement Wi-Fi scanning or
 * the update stream to restyle a menu — and they are rendered **bare**. Each
 * one already IS a full-screen overlay; boxing one nests a position:fixed layer
 * inside a flex panel, which is what shattered the Wi-Fi page and painted it
 * black. Restyle them through the --gc-overlay-* variables in theme.css
 * instead.
 *
 * MENU is checked against the host's page list two ways: at runtime, by the
 * host, which names anything unreachable in Settings → Themes; and in CI, by
 * scripts/check-theme.mjs against the `settings.pages` block in theme.json.
 * Both exist because leaving an entry out has shipped twice — `catalog`, which
 * left both bundled themes unable to install an emulator, and `storage`, which
 * was missing from the host map itself.
 */
const MENU = [
  { id: 'wifi', icon: '📶', label: 'Wi-Fi', sub: 'Manage networks' },
  { id: 'audio', icon: '🔊', label: 'Audio', sub: 'Volume, output & UI sounds' },
  { id: 'bluetooth', icon: '◉', label: 'Bluetooth', sub: 'Devices & pairing' },
  { id: 'storage', icon: '💾', label: 'Storage', sub: 'External disks & safe eject' },
  { id: 'standby', icon: '🌙', label: 'Standby', sub: 'Screensaver & low power' },
  { id: 'themes', icon: '🎨', label: 'Themes', sub: 'Change the look of the UI' },
  { id: 'catalog', icon: '🎮', label: 'Emulators & apps', sub: 'Add or remove systems' },
  { id: 'bios', icon: '🧩', label: 'BIOS', sub: 'System files each console needs' },
  { id: 'update', icon: '↑', label: 'Update', sub: 'Check for updates' },
  { id: 'desktop', icon: '⎋', label: 'Desktop Mode', sub: 'Return to system', danger: true },
]

export const createSettings = (sdk) => {
  const { html, useState, useEffect } = sdk.ui

  return ({ onClose }) => {
    const [page, setPage] = useState(null)
    const [focus, setFocus] = useState(0)
    const Pages = sdk.defaults.DefaultSettingsPages

    useEffect(() => {
      if (page) return   // the sub-page brings its own bindings
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move'); setFocus(f => Math.max(0, f - 1))
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move'); setFocus(f => Math.min(MENU.length - 1, f + 1))
        }),
        sdk.input.onGp('gp:confirm', () => {
          sdk.system.playSound('confirm')
          setFocus(f => { setPage(MENU[f].id); return f })
        }),
        sdk.input.onGp('gp:back', onClose),
        sdk.input.onGp('gp:menu', onClose),
      ]
      return () => offs.forEach(off => off())
    }, [page, onClose])

    if (page) {
      const P = Pages[page]
      // Undefined means the host renamed or dropped a page and this menu still
      // lists it. Say so rather than rendering nothing, which is the exact
      // symptom that made the original bug so hard to see.
      if (!P) {
        return html`
          <${sdk.defaults.SettingsOverlay} onClose=${onClose}>
            <${sdk.defaults.BackBar} label="SETTINGS" onBack=${() => setPage(null)} />
            <p class="dr-missing">This build has no “${page}” page.</p>
          <//>`
      }
      return html`<${P} onClose=${onClose} onBack=${() => setPage(null)} />`
    }

    return html`
      <${sdk.defaults.SettingsOverlay} onClose=${onClose}>
        <${sdk.defaults.Label} text="SETTINGS" />
        <div class="dr-menu">
          ${MENU.map((it, i) => html`
            <div key=${it.id} class="dr-menu-row" data-on=${focus === i ? '1' : '0'}
                 data-danger=${it.danger ? '1' : '0'}
                 onClick=${() => setPage(it.id)}>
              <span class="dr-menu-icon">${it.icon}</span>
              <span class="dr-menu-text"><b>${it.label}</b><i>${it.sub}</i></span>
              <span class="dr-menu-chevron">›</span>
            </div>`)}
        </div>
        <div class="dr-hint">↑↓ Navigate · ✕ Select · ○ Close</div>
      <//>`
  }
}
