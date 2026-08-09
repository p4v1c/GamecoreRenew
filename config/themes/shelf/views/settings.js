/**
 * The settings menu — the drawer under the shelf.
 *
 * Warm near-black and seal gold rather than the paper of the screens behind
 * it, and that is deliberate rather than a lapse: Wi-Fi, audio, Bluetooth,
 * standby and the updater are the host's pages, reused whole, and every one of
 * them writes its text in hardcoded white. A light panel would hand you a menu
 * in paper and a Wi-Fi page in white-on-white. So the menu joins them instead,
 * and `--gc-overlay-*` in theme.css brings them the rest of the way here.
 *
 * They are rendered bare, never boxed. Each one already *is* a full-screen
 * overlay; nesting a position:fixed layer inside a flex panel is what shatters
 * their layout.
 */
const MENU = [
  { id: 'wifi', icon: '📶', label: 'Wi-Fi', sub: 'Networks and passwords' },
  { id: 'audio', icon: '🔊', label: 'Audio', sub: 'Volume and output' },
  { id: 'bluetooth', icon: '◉', label: 'Bluetooth', sub: 'Pads and headsets' },
  { id: 'standby', icon: '🌙', label: 'Standby', sub: 'Screensaver and sleep' },
  { id: 'catalog', icon: '🎮', label: 'Emulators & apps', sub: 'Add a system, or take one off the shelf' },
  // bios and storage were in the host's menu and in none of this one, so a
  // player on this theme could not reach either. See settings.pages in
  // theme.json — the host now says so out loud in Settings → Themes.
  { id: 'bios', icon: '🧩', label: 'BIOS', sub: 'The system files a console needs to start' },
  { id: 'storage', icon: '💾', label: 'Storage', sub: 'External disks, and how to unplug one safely' },
  { id: 'themes', icon: '▧', label: 'Themes', sub: 'Change how this looks' },
  { id: 'update', icon: '↑', label: 'Update', sub: 'Check for a new version' },
  { id: 'desktop', icon: '⎋', label: 'Desktop', sub: 'Leave for the system', danger: true },
]

export const createSettings = (sdk, ownPages = {}) => {
  const { html, useState, useEffect, useRef } = sdk.ui

  return ({ onClose }) => {
    const [page, setPage] = useState(null)
    const [focus, setFocus] = useState(0)
    const Pages = { ...sdk.defaults.DefaultSettingsPages, ...ownPages }

    // The scrim fades in when the menu OPENS, and never again.
    //
    // Opening a sub-page unmounts this markup and coming back mounts it afresh,
    // so the fade replayed on the way back: for the length of it the backdrop
    // was transparent and the dashboard showed straight through, which reads as
    // the menu having closed and reopened. The component itself stays mounted
    // across that, so a ref survives where the DOM node does not.
    const opened = useRef(false)
    useEffect(() => { opened.current = true }, [])

    useEffect(() => {
      if (page) return   // the sub-page brings its own bindings
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move'); setFocus((f) => (f - 1 + MENU.length) % MENU.length)
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move'); setFocus((f) => (f + 1) % MENU.length)
        }),
        sdk.input.onGp('gp:confirm', () => {
          sdk.system.playSound('confirm'); setFocus((f) => { setPage(MENU[f].id); return f })
        }),
        sdk.input.onGp('gp:back', onClose),
      ]
      return () => offs.forEach((off) => off())
    }, [page, onClose])

    if (page) {
      const P = Pages[page]
      return html`<${P} onClose=${onClose} onBack=${() => setPage(null)} />`
    }

    return html`
      <div class="cz-scrim" data-enter=${opened.current ? '0' : '1'}
           onClick=${(e) => e.target === e.currentTarget && onClose()}>
        <div class="cz-panel">
          <div class="cz-panel-title">Settings</div>
          ${MENU.map((it, i) => html`
            <div key=${it.id} class="cz-row" data-on=${focus === i ? '1' : '0'}
                 data-danger=${it.danger ? '1' : '0'} onClick=${() => setPage(it.id)}>
              <span class="cz-row-icon">${it.icon}</span>
              <span class="cz-row-text"><b>${it.label}</b><i>${it.sub}</i></span>
              <span class="cz-row-chevron">›</span>
            </div>`)}
          <div class="cz-hint cz-hint-modal">↑↓ Move · ✕ Open · ○ Close</div>
        </div>
      </div>`
  }
}
