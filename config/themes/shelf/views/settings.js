/**
 * Settings — the drawer under the shelf, as a numbered rail.
 *
 * The reference capture is a two-column screen: a rail of categories on the
 * left, the category's contents on the right, both visible at once. That is
 * not buildable here and the reason is structural rather than aesthetic. Every
 * page in `sdk.defaults.DefaultSettingsPages` renders its own `<Overlay>`,
 * which is `position:fixed; inset:0` (frontend/src/components/ui/index.tsx).
 * The only handles a theme gets on it are `--gc-overlay-{scrim,blur,panel,
 * border,radius}` — colour, blur and corners. None of them insets the layer.
 * So a page shown "on the right" covers the rail no matter what, and boxing it
 * to force it into a column nests position:fixed inside a flex panel, which is
 * the exact thing that shattered the Wi-Fi page and painted it black.
 *
 * What survives of the capture is what carried its meaning: the numbered rail,
 * and the live value at the end of every line — the SSID you are on, how many
 * pads answered, how many BIOS sets are complete. That is the part that tells
 * you where to go before you go there, and it is all read from the box.
 *
 * The palette does NOT follow the capture. It was drawn in teal on paper, and
 * the host pages behind these rows write their text in hardcoded white — a
 * paper rail handing over to a white-on-white Wi-Fi page is the seam this
 * theme's overlays were made warm near-black to avoid in the first place.
 *
 * Every value here is read or it is absent. A row whose endpoint failed shows
 * nothing rather than a plausible number: the capture's own figures (−42 dBm,
 * 82 %, `2.4.0 → 2.4.2`) have no source on this box, and a rail that invents
 * them is a rail nobody can trust for the ones that are real.
 */

/**
 * Eight rows, and the four that hide under `System`.
 *
 * `Display` is not here. Resolution and refresh rate need a mode switch whose
 * safety net — revert unless confirmed — would have to run in the very surface
 * a bad mode makes invisible, and VSync is per-emulator, written by configgen,
 * so one global switch would misstate what it governs.
 *
 * `Controllers` is this theme's own page rather than a host one: the pad
 * tester lives on □ / `gp:guide` and the shell owns whether it is up, so a
 * menu cannot open it. The page states what is connected and says where the
 * three controller settings actually live.
 */
const CATS = [
  { id: 'wifi',        n: '01', label: 'Wi-Fi',            sub: 'Networks and passwords' },
  { id: 'bluetooth',   n: '02', label: 'Bluetooth',        sub: 'Pads and headsets' },
  { id: 'audio',       n: '03', label: 'Audio',            sub: 'Volume, output and haptics' },
  { id: 'controllers', n: '04', label: 'Controllers',      sub: 'What is connected, and where its settings are' },
  { id: 'catalog',     n: '05', label: 'Emulators & apps', sub: 'Add a system, or take one off the shelf' },
  { id: 'bios',        n: '06', label: 'BIOS',             sub: 'The system files a console needs to start' },
  { id: 'themes',      n: '07', label: 'Themes',           sub: 'Change how this looks' },
  { id: 'system',      n: '08', label: 'System',           sub: 'Updates, standby, disks, desktop', group: true },
]

// The host has ten settings pages and this rail has eight rows, which is not a
// contradiction: theme.json declares what is REACHABLE, not what is listed.
// These four are reached one level down rather than being left without a door
// — omitting one is how `catalog` and `storage` shipped unreachable twice.
const SYSTEM = [
  { id: 'update',  label: 'Update',  sub: 'Check for a new version of GameCore' },
  { id: 'standby', label: 'Standby', sub: 'Screensaver and sleep' },
  { id: 'storage', label: 'Storage', sub: 'External disks, and how to unplug one safely' },
  { id: 'desktop', label: 'Desktop', sub: 'Leave for the system session', danger: true },
]

const SYSTEM_IDX = CATS.findIndex((c) => c.id === 'system')

export const createSettings = (sdk, ownPages = {}) => {
  const { html, useState, useEffect, useRef } = sdk.ui

  return ({ onClose }) => {
    const [page, setPage] = useState(null)
    // The rail and the System sub-list are one screen with two contents, not
    // two screens: staying mounted is what lets coming back from Storage land
    // on System again instead of at the top of the rail.
    const [inSystem, setInSystem] = useState(false)
    const [focus, setFocus] = useState(0)
    const [meta, setMeta] = useState({})
    const Pages = { ...sdk.defaults.DefaultSettingsPages, ...ownPages }

    // The scrim fades in when the menu OPENS, and never again. Opening a
    // sub-page unmounts this markup and coming back mounts it afresh, so the
    // fade replayed on the way back and the dashboard showed through for its
    // duration — which reads as the menu having closed and reopened.
    const opened = useRef(false)
    useEffect(() => { opened.current = true }, [])

    const focusRef = useRef(focus)
    useEffect(() => { focusRef.current = focus }, [focus])

    /**
     * The values at the end of the rows.
     *
     * Eight independent reads, each landing on its own. One endpoint being
     * down leaves one row without a value and the other seven intact — the
     * alternative, a single Promise.all, loses the whole rail to whichever
     * service happens to be restarting.
     */
    useEffect(() => {
      let alive = true
      const put = (k, v) => { if (alive && v) setMeta((m) => ({ ...m, [k]: v })) }
      const api = sdk.api

      api.wifi.status()
        .then((s) => put('wifi', s.connected ? s.ssid
          : s.ethernet && s.ethernet.connected ? 'Wired' : 'Not connected'))
        .catch(() => {})

      api.bluetooth.devices()
        .then((ds) => put('bluetooth', `${ds.filter((d) => d.connected).length} connected`))
        .catch(() => {})

      api.audio.sinks()
        .then((ss) => { const d = ss.find((s) => s.default); put('audio', d && d.name) })
        .catch(() => {})

      api.catalog.list()
        .then((cs) => put('catalog', `${cs.filter((c) => c.installed).length} installed`))
        .catch(() => {})

      // `status` is the worst state among the REQUIRED files, which is the
      // same verdict the BIOS page paints its dots with.
      api.bios.list()
        .then((bs) => put('bios', `${bs.filter((b) => b.status === 'ok').length}/${bs.length} ready`))
        .catch(() => {})

      sdk.themes.list()
        .then((i) => {
          const t = (i.themes || []).find((x) => x.id === i.active)
          put('themes', t ? t.name : 'Default')
        })
        .catch(() => {})

      api.sysinfo().then((si) => put('update', `v${si.version}`)).catch(() => {})

      api.standby.get()
        .then((s) => put('standby', s.enabled ? `On · ${s.screensaver_mins} min` : 'Off'))
        .catch(() => {})

      api.storage.list()
        .then((r) => {
          const n = (r.volumes || []).length
          put('storage', n === 1 ? '1 external disk' : `${n} external disks`)
        })
        .catch(() => {})

      // Pads come from the Gamepad API rather than from sysinfo. sysinfo's
      // controller list is `read_batteries()`, which only sees pads exposing a
      // sysfs battery — a wired pad has none and would be counted as absent.
      // The browser's list is what the whole UI is actually driven by.
      const pads = (navigator.getGamepads ? navigator.getGamepads() : []).filter(Boolean)
      put('controllers', pads.length === 1 ? '1 pad' : `${pads.length} pads`)

      return () => { alive = false }
    }, [])

    const list = inSystem ? SYSTEM : CATS

    const leaveSystem = () => {
      setInSystem(false)
      setFocus(SYSTEM_IDX)
    }

    useEffect(() => {
      if (page) return   // the sub-page brings its own bindings
      const len = list.length
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move'); setFocus((f) => (f - 1 + len) % len)
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move'); setFocus((f) => (f + 1) % len)
        }),
        sdk.input.onGp('gp:confirm', () => {
          const it = list[focusRef.current]
          if (!it) return
          sdk.system.playSound('confirm')
          if (it.group) { setInSystem(true); setFocus(0) } else setPage(it.id)
        }),
        sdk.input.onGp('gp:back', () => {
          if (inSystem) { sdk.system.playSound('back'); leaveSystem() } else onClose()
        }),
      ]
      return () => offs.forEach((off) => off())
    }, [page, inSystem, list, onClose])

    if (page) {
      const P = Pages[page]
      // A row whose page the host does not have would otherwise render as a
      // blank fixed layer with no way out — visibly a crash, and unreachable
      // by ○ because the missing page is what would have bound it.
      if (!P) return html`
        <div class="cz-scrim" data-enter="0" onClick=${() => setPage(null)}>
          <div class="cz-panel">
            <div class="cz-panel-title">Settings</div>
            <div class="cz-note">This build has no “${page}” page.</div>
          </div>
        </div>`
      return html`<${P} onClose=${onClose} onBack=${() => setPage(null)} />`
    }

    return html`
      <div class="cz-scrim" data-enter=${opened.current ? '0' : '1'}
           onClick=${(e) => e.target === e.currentTarget && onClose()}>
        <div class="cz-panel">
          <div class="cz-panel-title">
            ${inSystem
              ? html`<button class="cz-panel-back" onClick=${leaveSystem}>‹</button><span>Settings · System</span>`
              : html`<span>Settings</span>`}
          </div>

          ${list.map((it, i) => html`
            <div key=${it.id} class="cz-set-row" data-on=${focus === i ? '1' : '0'}
                 data-danger=${it.danger ? '1' : '0'}
                 onClick=${() => { if (it.group) { setInSystem(true); setFocus(0) } else setPage(it.id) }}>
              ${it.n ? html`<span class="cz-set-num">${it.n}</span>` : null}
              <span class="cz-set-text"><b>${it.label}</b><i>${it.sub}</i></span>
              <span class="cz-set-meta">${meta[it.id] || ''}</span>
              <span class="cz-set-chevron">›</span>
            </div>`)}

          <div class="cz-hint cz-hint-modal">
            ${inSystem ? '↑↓ Move · ✕ Open · ○ Back' : '↑↓ Move · ✕ Open · ○ Close'}
          </div>
        </div>
      </div>`
  }
}
