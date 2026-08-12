/**
 * Settings — the reference capture's screen, not a menu that leads to it.
 *
 * The capture is ONE screen: a numbered rail on the left that never leaves,
 * the category's contents beside it, and for Wi-Fi and Bluetooth a third
 * column of detail. An earlier pass here read that as impossible, and it was
 * — for as long as every category resolved to `DefaultSettingsPages`, whose
 * pages are each a `position:fixed; inset:0` overlay that covers the rail
 * whatever a theme does to it.
 *
 * The way through is the one the SDK documents: `{ ...DefaultSettingsPages,
 * ...ownPages }`. A page written here is ordinary markup, so it sits in the
 * middle column and the rail stays put. That is what let the rewrite happen
 * one category at a time — each finished page moved out of the host's
 * full-screen overlay and into this column — and all eight are here now, so
 * nothing on this screen opens an overlay any more.
 *
 * ⛔ Own pages are BARE. This frame carries the overlay, once. Wrapping a page
 * in a panel of its own is the nested position:fixed that shattered the Wi-Fi
 * page and painted it black, and the docstring in defaults.tsx still describes
 * the pages the old way — `summer/views/settings.js` and the SDK table are the
 * ones telling the truth.
 *
 * The palette is the capture's paper and teal rather than Shelf's gold, which
 * is the one deliberate reading of "the capture is the reference" worth
 * arguing about. It lives in `--set-acc` in theme.css: one variable, one line
 * to change if the shelf's gold should win instead.
 */
import { createUseSlow } from '../lib/slow.js'
import { createRows } from './pages/rows.js'
import { createWifiPage } from './pages/wifi.js'
import { createBluetoothPage } from './pages/bluetooth.js'
import { createControllersPage } from './pages/controllers.js'
import { createAudioPage } from './pages/audio.js'
import { createCatalogPage } from './pages/catalog.js'
import { createBiosPage } from './pages/bios.js'
import { createThemesPage } from './pages/themes.js'
import { createSystemPage } from './pages/system.js'

/**
 * The rail. Eight rows where the capture has nine — `Display` is absent, and
 * that refusal is written up in the README: a mode switch whose "revert unless
 * confirmed" has to run inside the surface a bad mode makes invisible is a
 * safety net that cannot fire.
 *
 * `page` names the host page a row falls back to while it has no own page yet.
 * `system` fans out to four of them, which is why the rail can be eight rows
 * long and still declare all ten in theme.json.
 */
const CATS = [
  { id: 'wifi',        n: '01', label: 'Wi-Fi',            page: 'wifi' },
  { id: 'bluetooth',   n: '02', label: 'Bluetooth',        page: 'bluetooth' },
  { id: 'audio',       n: '03', label: 'Audio',            page: 'audio' },
  { id: 'controllers', n: '04', label: 'Controllers',      page: 'controllers' },
  { id: 'catalog',     n: '05', label: 'Emulators & apps', page: 'catalog' },
  { id: 'bios',        n: '06', label: 'BIOS',             page: 'bios' },
  { id: 'themes',      n: '07', label: 'Themes',           page: 'themes' },
  { id: 'system',      n: '08', label: 'System' },
]

// `update`, `standby`, `storage` and `desktop` no longer have rail rows of
// their own: the System page carries the first three, and leaving for the
// desktop is in the power menu, where the capture puts it. theme.json still
// declares all ten, because the declaration is about what a player can REACH
// and every one of those settings is reachable — see the README.

export const createSettings = (sdk, ownPages = {}, parts = {}) => {
  const { html, useState, useEffect, useRef } = sdk.ui
  const TopBar = parts.TopBar

  // Pages written for this screen, keyed the way the rail is. Every category
  // has one now; `ownPages.inline` is the seam a fork would use to replace one
  // without touching this file. A category with no entry here still resolves
  // through `DefaultSettingsPages` and opens as the host's overlay, which is
  // what made the rewrite possible page by page instead of all at once.
  const Rows = createRows(sdk)
  const useSlow = createUseSlow(sdk)
  const OwnPages = {
    wifi: createWifiPage(sdk, useSlow),
    bluetooth: createBluetoothPage(sdk, useSlow),
    audio: createAudioPage(sdk, Rows),
    controllers: createControllersPage(sdk, Rows),
    catalog: createCatalogPage(sdk),
    bios: createBiosPage(sdk),
    themes: createThemesPage(sdk, Rows),
    system: createSystemPage(sdk, Rows),
    ...ownPages.inline,
  }

  return ({ onClose }) => {
    const [cat, setCat] = useState('wifi')
    const [railFocus, setRailFocus] = useState(0)
    // 'rail' or 'page'. The capture has no visible cursor, so which column
    // answers the d-pad has to be legible from the highlight alone.
    const [zone, setZone] = useState('rail')
    const [meta, setMeta] = useState({})
    // The raw answers behind the rail's values. Wi-Fi and Bluetooth need the
    // same two requests the rail already made, so the page opens with them in
    // hand instead of fetching them a second time behind an empty card.
    const [seed, setSeed] = useState({})

    const railFocusRef = useRef(railFocus)
    useEffect(() => { railFocusRef.current = railFocus }, [railFocus])
    const zoneRef = useRef(zone)
    useEffect(() => { zoneRef.current = zone }, [zone])

    /**
     * The values at the end of the rows, and in the breadcrumb.
     *
     * Eight independent reads, each landing on its own: one endpoint being down
     * leaves one row without a value and the other seven intact. Nothing here
     * falls back to a plausible string — the capture's own figures have no
     * source on this box, and a rail that invents them cannot be trusted for
     * the ones that are real.
     */
    useEffect(() => {
      let alive = true
      const put = (k, v) => { if (alive && v) setMeta((m) => ({ ...m, [k]: v })) }
      const api = sdk.api

      const keep = (k, v) => { if (alive) setSeed((s) => ({ ...s, [k]: v })) }

      api.wifi.status()
        .then((s) => {
          keep('wifi', s)
          put('wifi', s.connected ? s.ssid
            : s.ethernet && s.ethernet.connected ? 'Wired' : 'Not connected')
        })
        .catch(() => {})
      api.bluetooth.devices()
        .then((ds) => {
          keep('bluetooth', ds)
          put('bluetooth', `${ds.filter((d) => d.connected).length} connected`)
        })
        .catch(() => {})
      api.audio.sinks()
        .then((ss) => { const d = ss.find((s) => s.default); put('audio', d && d.name) })
        .catch(() => {})
      api.catalog.list()
        .then((cs) => put('catalog', `${cs.filter((c) => c.installed).length} installed`))
        .catch(() => {})
      api.bios.list()
        .then((bs) => put('bios', `${bs.filter((b) => b.status === 'ok').length}/${bs.length} ready`))
        .catch(() => {})
      sdk.themes.list()
        .then((i) => {
          const t = (i.themes || []).find((x) => x.id === i.active)
          put('themes', t ? t.name : 'Default')
        })
        .catch(() => {})
      api.sysinfo().then((si) => put('system', `v${si.version}`)).catch(() => {})

      // Pads come from the Gamepad API, not from sysinfo: that list is
      // `read_batteries()`, a sysfs scan that cannot see a wired pad, and this
      // row would report "no pad" to somebody holding one.
      const pads = (navigator.getGamepads ? navigator.getGamepads() : []).filter(Boolean)
      put('controllers', pads.length === 1 ? '1 pad' : `${pads.length} pads`)

      return () => { alive = false }
    }, [])

    const list = CATS
    const current = CATS.find((c) => c.id === cat) || CATS[0]
    const Inline = OwnPages[cat]

    const activate = (it) => {
      if (!it) return
      sdk.system.playSound('confirm')
      setCat(it.id)
      setZone('page')
    }

    // Rail bindings. Suspended while a host overlay is up (it brings its own)
    // and while the middle column has focus (the page brings its own).
    useEffect(() => {
      if (zone === 'page') return
      const len = list.length
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move'); setRailFocus((f) => (f - 1 + len) % len)
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move'); setRailFocus((f) => (f + 1) % len)
        }),
        sdk.input.onGp('gp:dpad-right', () => {
          const it = list[railFocusRef.current]
          if (it) { sdk.system.playSound('move'); setCat(it.id); setZone('page') }
        }),
        sdk.input.onGp('gp:confirm', () => activate(list[railFocusRef.current])),
        sdk.input.onGp('gp:back', onClose),
      ]
      return () => offs.forEach((off) => off())
    }, [zone, list, onClose])

    // Moving the rail cursor previews the category, the way the capture reads:
    // the highlighted row and the middle column always name the same thing.
    useEffect(() => {
      if (zone !== 'rail') return
      const it = CATS[railFocus]
      if (it) setCat(it.id)
    }, [railFocus, zone])

    const crumbMeta = meta[cat] || ''

    return html`
      <div class="cz-set" onClick=${(e) => e.target === e.currentTarget && onClose()}>
        <div class="cz-set-paper"></div>

        ${TopBar ? html`<${TopBar} onSettings=${() => {}} onPower=${() => {}} />` : null}

        <header class="cz-set-head">
          <h1 class="cz-set-title">Settings</h1>
          <div class="cz-set-crumb">
            <span class="cz-set-chip">${current.label.toUpperCase()}</span>
            <span>${current.label}${crumbMeta ? ` · ${crumbMeta}` : ''}</span>
          </div>
        </header>

        <div class="cz-set-body">
          <nav class="cz-set-rail" data-zone=${zone === 'rail' ? 'on' : 'off'}>
            ${list.map((it, i) => html`
              <div key=${it.id} class="cz-set-row"
                   data-on=${zone === 'rail' && railFocus === i ? '1' : '0'}
                   data-sel=${it.id === cat ? '1' : '0'}
                   data-danger=${it.danger ? '1' : '0'}
                   onClick=${() => { setRailFocus(i); activate(it) }}>
                ${it.n ? html`<span class="cz-set-num">${it.n}</span>` : null}
                <span class="cz-set-label">
                  <b>${it.label}</b>
                  <i>${meta[it.id] || ''}</i>
                </span>
              </div>`)}
          </nav>

          ${Inline
            ? html`<${Inline} seed=${seed[cat]} active=${zone === 'page'}
                              onLeave=${() => { sdk.system.playSound('back'); setZone('rail') }}
                              onClose=${onClose} />`
            // A category with no page renders as words rather than as
            // `undefined` handed to React, which throws — and under the shell's
            // error boundary that hands the whole frontend back to the default.
            // A theme going dark because one page was renamed is the quiet
            // failure this whole guard exists to stop.
            : html`
              <section class="cz-set-main cz-set-main-empty">
                <div class="cz-set-h">${current.label}</div>
                <p class="cz-set-sub">This build has no “${cat}” page.</p>
              </section>`}
        </div>

        <footer class="cz-set-foot">
          <!-- The capture prints a library total here ("51 games across 11
               systems · 194h played"). It is real data, but it costs a walk of
               every system's game list plus the playtime table to compute, on a
               screen that is not about the library — so the corner stays empty
               rather than repeating a number the rail already shows. -->
          <span class="cz-set-foot-l"></span>
          <span class="cz-set-hints">
            <span><kbd>✕</kbd>Select</span>
            <span><kbd>○</kbd>Back</span>
            <span><kbd>□</kbd>Controller</span>
          </span>
        </footer>
      </div>`
  }
}
