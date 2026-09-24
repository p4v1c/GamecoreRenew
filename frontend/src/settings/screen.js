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
 * This screen is not Shelf's, and it is not a theme's at all any more. Three
 * surfaces draw it — Shelf, Summer, and the built-in default — and one copy is
 * the only way a fix reaches all three.
 *
 * It lived under `config/themes/_shared/` first, which was the right idea in
 * the wrong place, for two reasons that both bit:
 *
 *   · **The updater.** `_shared` needed a `theme.json` purely so
 *     `update/linux.sh` would compare its version and deliver it, and twice a
 *     fix here shipped without a bump and simply never arrived on the box.
 *     Code in the bundle has no version to forget.
 *   · **Safe mode.** The built-in UI is what `themeSafety.ts` falls back TO
 *     when a theme crashes — screen by screen first, then wholesale after
 *     CRASH_LIMIT. A default settings screen reaching into a directory shipped
 *     over the air would share the failure it exists to catch. Here it is in
 *     the bundle, present whenever the front end is.
 *
 * Themes reach it through `sdk.defaults.createSettings`, the same way they
 * already reach `sdk.defaults.DefaultKeyboard`.
 *
 * It carries **no colour**. Every class is `gcs-*` and each surface supplies
 * the palette: Shelf paints it paper and teal, Summer sea glass and mandarin,
 * the default dark and violet. Anything hardcoded here would be one of them
 * imposing on the other two, which is why the classes stopped being `cz-`.
 */
import { createUseSlow } from './slow.js'
import { versionLabel } from './list.js'
import { createRows } from './rows.js'
import { createDialogs } from './dialog.js'
import { createWifiPage } from './wifi.js'
import { createBluetoothPage } from './bluetooth.js'
import { createDisplayPage } from './display.js'
import { createControllersPage } from './controllers.js'
import { createAudioPage } from './audio.js'
import { createCatalogPage } from './catalog.js'
import { createBiosPage } from './bios.js'
import { createThemesPage } from './themes.js'
import { createSystemPage } from './system.js'
import { PadKey } from '../lib/padKey.js'

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
 *
 * `group` is the chapter Shelf's page header names ("PAGE 03 / EXPERIENCE").
 * It is navigation, not a category: there is no General page behind it.
 */
const CATS = [
  { id: 'wifi',        n: '01', label: 'Wi-Fi',            page: 'wifi',        group: 'Connections' },
  { id: 'bluetooth',   n: '02', label: 'Bluetooth',        page: 'bluetooth',   group: 'Connections' },
  { id: 'display',     n: '03', label: 'Display',          page: 'display',     group: 'Experience' },
  { id: 'audio',       n: '04', label: 'Audio',            page: 'audio',       group: 'Experience' },
  { id: 'controllers', n: '05', label: 'Controllers',      page: 'controllers', group: 'Experience' },
  { id: 'catalog',     n: '06', label: 'Emulators & apps', page: 'catalog',     group: 'Collection' },
  { id: 'bios',        n: '07', label: 'BIOS',             page: 'bios',        group: 'Collection' },
  { id: 'themes',      n: '08', label: 'Themes',           page: 'themes',      group: 'Collection' },
  { id: 'system',      n: '09', label: 'System',                                group: 'Console' },
]

// `update`, `standby`, `storage` and `desktop` no longer have rail rows of
// their own: the System page carries the first three, and leaving for the
// desktop is in the power menu, where the capture puts it. theme.json still
// declares all ten, because the declaration is about what a player can REACH
// and every one of those settings is reachable — see the README.

/**
 * Line icons for the index layout, 24×24, stroked in `currentColor`. Drawn for
 * this screen rather than borrowed, so the bundle carries no icon set for nine
 * glyphs.
 */
const ICONS = {
  wifi: 'M4 9.5a12 12 0 0 1 16 0M7 13a7.5 7.5 0 0 1 10 0M10 16.5a3 3 0 0 1 4 0M12 20h.01',
  bluetooth: 'M7 7l10 10-5 4V3l5 4L7 17',
  display: 'M3 5h18v11H3zM8 20h8M12 16v4',
  audio: 'M4 9v6h4l5 4V5L8 9zM16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11',
  controllers: 'M6 9h12a4 4 0 0 1 3.9 4.9l-.8 3.4a2 2 0 0 1-3.4.9L15 16H9l-2.7 2.2a2 2 0 0 1-3.4-.9l-.8-3.4A4 4 0 0 1 6 9zM8 11.5v3M6.5 13h3M15.5 12.5h.01M17.5 14h.01',
  catalog: 'M4 4h4v16H4zM10 4h4v16h-4zM16 5l4 1-3 14-4-1z',
  bios: 'M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4',
  themes: 'M12 3a9 9 0 1 0 0 18c1.1 0 1.5-.8 1.5-1.6 0-1.2-.9-1.7-.9-2.6 0-.9.7-1.3 1.6-1.3H16a5 5 0 0 0 5-5c0-4.1-4-7.5-9-7.5zM7.5 11h.01M10 7.5h.01M14.5 7.5h.01',
  system: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9L7 7M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1',
}

/**
 * @param parts.TopBar      drawn above the screen; the built-in UI has none here
 * @param parts.skin        extra class on the root, carrying the palette
 * @param parts.Background  the theme's own Home background component. Drawn as
 *                          this screen's first layer, so Settings stands on
 *                          the very wall — or the very artwork — Home does,
 *                          rendered by the same code, rather than on a copy
 *                          of it that drifts. Without one, the legacy
 *                          `.gcs-set-paper` layer paints as before.
 * @param parts.layout      'rail' (default): the numbered rail beside the
 *                          page. 'index': a category list that opens one page
 *                          at a time, with Back returning to the list — Orbit.
 * @param parts.pager       L1/R1 change category whenever no dialog is open,
 *                          and the page names its place ("PAGE 01 / …") — Shelf.
 * @param parts.detail      how pages show a network's or a device's detail:
 *                          'dialog' (Orbit), 'inline' (Shelf), or absent for
 *                          the layout the built-in UI and Summer have always
 *                          drawn. Absent changes nothing for them.
 */
export const createSettings = (sdk, ownPages = {}, parts = {}) => {
  const { html, useState, useEffect, useRef } = sdk.ui
  const TopBar = parts.TopBar
  const Background = parts.Background
  const layout = parts.layout === 'index' ? 'index' : 'rail'
  const pager = !!parts.pager
  const detail = parts.detail === 'dialog' || parts.detail === 'inline' ? parts.detail : undefined
  /**
   * An extra class on this screen's root, for whoever supplies the palette.
   *
   * The `gcs-*` rules carry no colour, so somebody has to. A theme does it from
   * its own stylesheet on `:root`, which is enough while its stylesheet is the
   * only one loaded. The built-in default cannot: its palette ships in the
   * bundle and is therefore ALWAYS loaded, including while a theme is active
   * and safe mode has swapped just this one screen back to the default.
   *
   * Hence a class rather than `:root`. `.gcs-set.gcs-skin-default` outranks a
   * theme's `:root` on specificity, so each surface keeps its own colours no
   * matter which stylesheets happen to be present.
   */
  const skin = parts.skin ? ` ${parts.skin}` : ''

  // Pages written for this screen, keyed the way the rail is. Every category
  // has one now; `ownPages.inline` is the seam a fork would use to replace one
  // without touching this file. A category with no entry here still resolves
  // through `DefaultSettingsPages` and opens as the host's overlay, which is
  // what made the rewrite possible page by page instead of all at once.
  const Rows = createRows(sdk)
  const useSlow = createUseSlow(sdk)
  const { Dialog, useDialogOpen } = createDialogs(sdk)
  const OwnPages = {
    wifi: createWifiPage(sdk, useSlow, Dialog),
    bluetooth: createBluetoothPage(sdk, useSlow, Dialog),
    display: createDisplayPage(sdk, Rows, Dialog),
    audio: createAudioPage(sdk, Rows),
    controllers: createControllersPage(sdk, Rows),
    catalog: createCatalogPage(sdk),
    bios: createBiosPage(sdk),
    themes: createThemesPage(sdk, Rows),
    system: createSystemPage(sdk, Rows),
    ...ownPages.inline,
  }

  const Icon = ({ id }) => html`
    <svg class="gcs-set-icon" viewBox="0 0 24 24" width="26" height="26" aria-hidden="true"
         fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d=${ICONS[id] || ICONS.system} />
    </svg>`

  return ({ onClose }) => {
    const [cat, setCat] = useState('wifi')
    const [railFocus, setRailFocus] = useState(0)
    // 'rail' or 'page'. The capture has no visible cursor, so which column
    // answers the d-pad has to be legible from the highlight alone. In the
    // index layout 'rail' is the category list.
    const [zone, setZone] = useState('rail')
    const [meta, setMeta] = useState({})
    // The raw answers behind the rail's values. Wi-Fi and Bluetooth need the
    // same two requests the rail already made, so the page opens with them in
    // hand instead of fetching them a second time behind an empty card.
    const [seed, setSeed] = useState({})
    // A dialog anywhere on this screen owns the pad. Nothing below it — the
    // rail, the index, L1/R1, ○ closing the screen — may answer until it goes.
    const dialogOpen = useDialogOpen()

    const railFocusRef = useRef(railFocus)
    useEffect(() => { railFocusRef.current = railFocus }, [railFocus])
    const zoneRef = useRef(zone)
    useEffect(() => { zoneRef.current = zone }, [zone])
    const catRef = useRef(cat)
    useEffect(() => { catRef.current = cat }, [cat])

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
      api.sysinfo().then((si) => put('system', versionLabel(si.version))).catch(() => {})

      // Pads come from the Gamepad API, not from sysinfo: that list is
      // `read_batteries()`, a sysfs scan that cannot see a wired pad, and this
      // row would report "no pad" to somebody holding one.
      const pads = (navigator.getGamepads ? navigator.getGamepads() : []).filter(Boolean)
      put('controllers', pads.length === 1 ? '1 pad' : `${pads.length} pads`)

      // …and it says "Auto setup off" instead when it is, which is the point of
      // asking here at all. Somebody whose new pad does nothing opens Settings
      // and reads this rail; without this they would have to guess that the
      // answer is one screen further in, behind a row that looks fine.
      // Overwrites the pad count on purpose: the two never both matter, and the
      // one that explains a dead controller is the one to show.
      api.controllers.autoconfig()
        .then((a) => { if (!a.enabled) put('controllers', 'Auto setup off') })
        .catch(() => {})

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

    // Leaving a page. In the index layout the list comes back with the cursor
    // on the category just left, because `railFocus` never moved while the
    // page was open — the place a player returns to is the place they left.
    const leave = () => { sdk.system.playSound('back'); setZone('rail') }

    // Rail bindings. Suspended while a host overlay is up (it brings its own),
    // while the middle column has focus (the page brings its own), and while
    // any dialog on this screen is open (it owns the pad).
    useEffect(() => {
      if (zone === 'page' || dialogOpen) return
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
    }, [zone, list, onClose, dialogOpen])

    // L1 / R1 — the previous and next category, from anywhere on the screen
    // except under a dialog. The cursor lands on the rail row, which is where
    // the new category is named, so the next ✕ or → goes into it.
    useEffect(() => {
      if (!pager || dialogOpen) return
      const step = (d) => {
        const len = list.length
        const at = list.findIndex((c) => c.id === catRef.current)
        const next = (Math.max(0, at) + d + len) % len
        sdk.system.playSound('move')
        setRailFocus(next); setCat(list[next].id); setZone('rail')
      }
      const offs = [
        sdk.input.onGp('gp:l1', () => step(-1)),
        sdk.input.onGp('gp:r1', () => step(1)),
      ]
      return () => offs.forEach((off) => off())
    }, [dialogOpen, list])

    // Moving the rail cursor previews the category, the way the capture reads:
    // the highlighted row and the middle column always name the same thing.
    // Not in the index layout, where the list IS the screen and a page only
    // exists once it has been opened.
    useEffect(() => {
      if (zone !== 'rail' || layout === 'index') return
      const it = CATS[railFocus]
      if (it) setCat(it.id)
    }, [railFocus, zone])

    // The focused category stays on screen. At 720p the rail is taller than
    // the space it has, and L1/R1 wrapping from Wi-Fi to System put the cursor
    // on a row nobody could see. `nearest` moves nothing when it already fits.
    const railRefs = useRef([])
    useEffect(() => {
      if (zone === 'rail') railRefs.current[railFocus]?.scrollIntoView?.({ block: 'nearest' })
    }, [railFocus, zone])

    const crumbMeta = meta[cat] || ''
    const pageNo = CATS.findIndex((c) => c.id === cat) + 1
    const pageActive = zone === 'page' && !dialogOpen

    const page = Inline
      ? html`<${Inline} seed=${seed[cat]} active=${pageActive} detail=${detail}
                        onLeave=${leave}
                        onLeft=${layout === 'index' ? () => {} : leave}
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
        </section>`

    const hints = layout === 'index'
      ? [['↑↓', 'Navigate'], ['✕', 'Select'], ['○', 'Back']]
      : pager
        ? [['↑↓', 'Browse'], ['✕', 'Select'], ['○', 'Back'], ['←→', 'Adjust'], ['L1 R1', 'Categories']]
        : [['✕', 'Select'], ['○', 'Back'], ['□', 'Controller']]

    const index = layout === 'index' && zone === 'rail'

    return html`
      <div class=${`gcs-set${skin}`} data-layout=${layout} data-pager=${pager ? '1' : '0'}
           data-bg=${Background ? 'theme' : 'own'} data-view=${index ? 'index' : 'page'}
           onClick=${(e) => e.target === e.currentTarget && onClose()}>
        ${Background
          ? html`<div class="gcs-set-bg" aria-hidden="true"><${Background} /></div>`
          : html`<div class="gcs-set-paper"></div>`}

        ${TopBar ? html`<${TopBar} onSettings=${() => {}} onPower=${() => {}} />` : null}

        ${layout === 'index' ? html`
          <header class="gcs-set-head">
            ${index ? null : html`
              <button type="button" class="gcs-set-back" onClick=${leave}
                      aria-label="Back to all settings">‹ All settings</button>`}
            <h1 class="gcs-set-title">${index ? 'Settings' : current.label}</h1>
            <!-- A pointer's way out. The pad's is ○ from the list; this sits
                 inside the screen, so an open dialog covers it like the rest. -->
            <button type="button" class="gcs-set-close" onClick=${onClose}
                    aria-label="Close settings">×</button>
          </header>` : html`
          <header class="gcs-set-head">
            <h1 class="gcs-set-title">Settings</h1>
            <div class="gcs-set-crumb">
              <span class="gcs-set-chip">${current.label.toUpperCase()}</span>
              <span>${current.label}${crumbMeta ? ` · ${crumbMeta}` : ''}</span>
            </div>
          </header>`}

        ${layout === 'index' ? html`
          <div class="gcs-set-body">
            ${index ? html`
              <nav class="gcs-set-index" aria-label="Settings categories">
                <p class="gcs-set-index-intro">Choose a category.</p>
                ${list.map((it, i) => html`
                  <button type="button" key=${it.id} class="gcs-set-index-row"
                          ref=${(el) => { railRefs.current[i] = el }}
                          data-on=${!dialogOpen && railFocus === i ? '1' : '0'}
                          aria-label=${meta[it.id] ? `${it.label}, ${meta[it.id]}` : it.label}
                          onClick=${() => { setRailFocus(i); activate(it) }}>
                    <${Icon} id=${it.id} />
                    <span class="gcs-set-label">
                      <b>${it.label}</b>
                      <i>${meta[it.id] || ''}</i>
                    </span>
                    <span class="gcs-set-chev" aria-hidden="true">›</span>
                  </button>`)}
              </nav>` : html`<div class="gcs-set-page" data-cat=${cat}>${page}</div>`}
          </div>` : html`
          <div class="gcs-set-body">
            <nav class="gcs-set-rail" data-zone=${zone === 'rail' ? 'on' : 'off'}
                 aria-label="Settings categories">
              ${list.map((it, i) => html`
                <div key=${it.id} class="gcs-set-row" role="button"
                     ref=${(el) => { railRefs.current[i] = el }}
                     aria-current=${it.id === cat ? 'page' : undefined}
                     data-on=${zone === 'rail' && !dialogOpen && railFocus === i ? '1' : '0'}
                     data-sel=${it.id === cat ? '1' : '0'}
                     data-danger=${it.danger ? '1' : '0'}
                     onClick=${() => { setRailFocus(i); activate(it) }}>
                  ${it.n ? html`<span class="gcs-set-num">${it.n}</span>` : null}
                  <span class="gcs-set-label">
                    <b>${it.label}</b>
                    <i>${meta[it.id] || ''}</i>
                  </span>
                  ${pager ? html`<span class="gcs-set-chev" aria-hidden="true">›</span>` : null}
                </div>`)}
            </nav>

            <div class="gcs-set-page" data-cat=${cat}>
              ${pager ? html`
                <div class="gcs-set-pagecrumb">
                  <span>PAGE ${String(pageNo).padStart(2, '0')} / ${current.group.toUpperCase()}</span>
                  <span class="gcs-set-pagekey">L1 / R1 · Categories</span>
                </div>` : null}
              ${page}
            </div>
          </div>`}

        <footer class="gcs-set-foot">
          <!-- The capture prints a library total here ("51 games across 11
               systems · 194h played"). It is real data, but it costs a walk of
               every system's game list plus the playtime table to compute, on a
               screen that is not about the library — so the corner stays empty
               rather than repeating a number the rail already shows. -->
          <span class="gcs-set-foot-l"></span>
          <span class="gcs-set-hints">
            ${hints.map(([k, v]) => html`<span key=${v}><${PadKey} k=${k} />${v}</span>`)}
          </span>
        </footer>
      </div>`
  }
}
