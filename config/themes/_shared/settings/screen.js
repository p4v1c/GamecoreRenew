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
 * ## Shared, and styled from outside
 *
 * This screen is not Shelf's any more. It lives in `config/themes/_shared/`
 * because two themes now draw it and one copy is the only way a fix reaches
 * both — the alternative was 1400 lines duplicated and drifting.
 *
 * `_shared` is not a theme and never appears in the picker: `list_themes()`
 * skips any directory starting with `_`. It carries a `theme.json` with a
 * version for one reason — `update/linux.sh` walks every directory under
 * `config/themes` and decides what to deliver by comparing that field, so
 * without it a fix here would install once and never update again.
 *
 * (Written without the glob it describes on purpose: a star-slash inside a
 * block comment ends the comment, and the rest of this file became code the
 * first time it was written the obvious way.)
 *
 * It carries **no colour**. Every class is `gcs-*` and every theme supplies the
 * palette: Shelf paints it paper and teal, Summer paints it sea glass and
 * amber. Anything hardcoded here would be one theme's decision imposed on the
 * other, which is the whole reason the classes stopped being called `cz-`.
 */
import { createUseSlow } from './slow.js'
import { createRows } from './rows.js'
import { createWifiPage } from './wifi.js'
import { createBluetoothPage } from './bluetooth.js'
import { createDisplayPage } from './display.js'
import { createControllersPage } from './controllers.js'
import { createAudioPage } from './audio.js'
import { createCatalogPage } from './catalog.js'
import { createBiosPage } from './bios.js'
import { createThemesPage } from './themes.js'
import { createSystemPage } from './system.js'

/**
 * The rail. Nine rows, the capture's own list.
 *
 * `Display` was absent for a long time, refused on the reasoning that its
 * "revert unless confirmed" would have to run inside the surface a bad mode
 * makes invisible. That was wrong twice over: the timer belongs in the backend,
 * which survives a black screen, and `xrandr` needs no privilege because it
 * acts on the session's own X server — the same unprivileged path `standby.py`
 * already uses for `xset`. What is still refused is VSync, which is written per
 * emulator by configgen and has no global switch to be.
 *
 * `page` names the host page a row falls back to while it has no own page yet.
 * `system` fans out to four of them, which is why the rail can be eight rows
 * long and still declare all ten in theme.json.
 */
const CATS = [
  { id: 'wifi',        n: '01', label: 'Wi-Fi',            page: 'wifi' },
  { id: 'bluetooth',   n: '02', label: 'Bluetooth',        page: 'bluetooth' },
  { id: 'display',     n: '03', label: 'Display',          page: 'display' },
  { id: 'audio',       n: '04', label: 'Audio',            page: 'audio' },
  { id: 'controllers', n: '05', label: 'Controllers',      page: 'controllers' },
  { id: 'catalog',     n: '06', label: 'Emulators & apps', page: 'catalog' },
  { id: 'bios',        n: '07', label: 'BIOS',             page: 'bios' },
  { id: 'themes',      n: '08', label: 'Themes',           page: 'themes' },
  { id: 'system',      n: '09', label: 'System' },
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
    display: createDisplayPage(sdk, Rows),
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
      <div class="gcs-set" onClick=${(e) => e.target === e.currentTarget && onClose()}>
        <div class="gcs-set-paper"></div>

        ${TopBar ? html`<${TopBar} onSettings=${() => {}} onPower=${() => {}} />` : null}

        <header class="gcs-set-head">
          <h1 class="gcs-set-title">Settings</h1>
          <div class="gcs-set-crumb">
            <span class="gcs-set-chip">${current.label.toUpperCase()}</span>
            <span>${current.label}${crumbMeta ? ` · ${crumbMeta}` : ''}</span>
          </div>
        </header>

        <div class="gcs-set-body">
          <nav class="gcs-set-rail" data-zone=${zone === 'rail' ? 'on' : 'off'}>
            ${list.map((it, i) => html`
              <div key=${it.id} class="gcs-set-row"
                   data-on=${zone === 'rail' && railFocus === i ? '1' : '0'}
                   data-sel=${it.id === cat ? '1' : '0'}
                   data-danger=${it.danger ? '1' : '0'}
                   onClick=${() => { setRailFocus(i); activate(it) }}>
                ${it.n ? html`<span class="gcs-set-num">${it.n}</span>` : null}
                <span class="gcs-set-label">
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
              <section class="gcs-set-main gcs-set-main-empty">
                <div class="gcs-set-h">${current.label}</div>
                <p class="gcs-set-sub">This build has no “${cat}” page.</p>
              </section>`}
        </div>

        <footer class="gcs-set-foot">
          <!-- The capture prints a library total here ("51 games across 11
               systems · 194h played"). It is real data, but it costs a walk of
               every system's game list plus the playtime table to compute, on a
               screen that is not about the library — so the corner stays empty
               rather than repeating a number the rail already shows. -->
          <span class="gcs-set-foot-l"></span>
          <span class="gcs-set-hints">
            <span><kbd>✕</kbd>Select</span>
            <span><kbd>○</kbd>Back</span>
            <span><kbd>□</kbd>Controller</span>
          </span>
        </footer>
      </div>`
  }
}
