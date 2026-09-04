/**
 * Settings → Wi-Fi, in this screen's own hand.
 *
 * Bare markup: the middle column and the detail column, nothing else. The
 * frame in views/settings.js carries the overlay — a panel of its own here is
 * the nested `position:fixed` that shattered this exact page once already.
 *
 * The behaviour stays the host's. Scanning, joining and disconnecting are
 * `sdk.api.wifi.*`, which is `nmcli` on the other end; this file decides what
 * the screen looks like and nothing about what it does. Rescanning happens
 * because `GET /networks` rescans, not because this asked it to.
 *
 * ## Where this departs from the capture, and why
 *
 * · **No ON/OFF switch.** The capture puts a toggle top-right. There is no
 *   route that turns the radio off — `wifi.py` connects and disconnects, and
 *   nothing more — so a switch here would be a control that governs nothing,
 *   which is worse than an absent one. The scanning indicator the capture also
 *   has is kept, and it is real.
 * · **Signal in per cent, not dBm.** nmcli reports link quality 0–100 and does
 *   not expose dBm without root. `-42 dBm` in the capture is a number this box
 *   cannot produce; 78 % is the same fact in the units the system actually
 *   measures it in.
 * · **No "Forget this network".** It would need `nmcli con delete`, which is a
 *   route that does not exist yet, and it destroys a saved profile — so it
 *   wants the same two-step protection as Forget mapping rather than a bare
 *   button. Named in the README as outstanding.
 * · **The password dialog holds the on-screen keyboard.** The capture draws a
 *   text field, which is a mouse-and-keyboard drawing: nobody typing a WPA
 *   passphrase from a sofa has either. `sdk.defaults.DefaultKeyboard` is the
 *   host's, brings its own bindings, and is the only way this is usable at all.
 *
 * Everything else in the detail column is now real. Gateway, DNS, MAC, band,
 * channel and link rate were the reason `/settings/wifi/details` and the three
 * new keys on `/status` were added — the capture asked for a panel the backend
 * could not fill, so the backend learned to fill it.
 */
const REFRESH_MS = 10000

/** 0–100 → four bars, the way the capture draws them. */
const barsFor = (signal) => Math.max(1, Math.min(4, Math.ceil((signal || 0) / 25)))

import { asList } from './list.js'

export const createWifiPage = (sdk, useSlow) => {
  const { html, useState, useEffect, useRef, React } = sdk.ui
  const Fragment = React.Fragment
  const Keyboard = sdk.defaults.DefaultKeyboard

  return ({ active, onLeave, seed }) => {
    const [nets, setNets] = useState([])
    // Seeded from the rail, which already fetched the status to put the SSID at
    // the end of this row. It is what the detail column is built from, so the
    // page opens with it rather than asking again and drawing a blank panel.
    const [status, setStatus] = useState(() => seed || null)
    const [detail, setDetail] = useState({})
    const [sel, setSel] = useState(0)
    const [asking, setAsking] = useState(null)   // ssid awaiting a password
    // Bumped every time the prompt opens and used as the keyboard's `key`, so
    // a prompt can only ever open on an empty field.
    //
    // This is a guard, not a repair: the dialog is unmounted on confirm, so the
    // keyboard already remounts with `useState('')` and the test below passes
    // without this line. It is here because the invariant is load-bearing and
    // invisible — a box sent `<old password><new password>` to NetworkManager
    // as one string, and nothing in this file would have looked wrong. A later
    // refactor that keeps the dialog mounted would reintroduce it silently.
    const [askSeq, setAskSeq] = useState(0)
    const [busy, setBusy] = useState(false)
    const [msg, setMsg] = useState('')
    const [loaded, setLoaded] = useState(false)
    // `GET /networks` rescans before it answers, so a couple of seconds is
    // normal and silence is not.
    const slow = useSlow(!loaded, 2500)

    const selRef = useRef(sel)
    useEffect(() => { selRef.current = sel }, [sel])
    const netsRef = useRef(nets)
    useEffect(() => { netsRef.current = nets }, [nets])

    const load = () => {
      sdk.api.wifi.status().then(setStatus).catch(() => {})
      sdk.api.wifi.networks()
        .then((list) => { setNets(asList(list)); setLoaded(true) })
        .catch(() => setLoaded(true))
      // Additive endpoint: a box whose backend predates it simply shows the
      // rows that do not depend on it, rather than an empty detail column.
      sdk.api.wifi.details()
        .then((rows) => setDetail(Object.fromEntries(asList(rows).map((r) => [r.ssid, r]))))
        .catch(() => {})
    }

    // Same race as Bluetooth's: the rail's status request and the player's
    // first press are not ordered, so the seed is taken whenever it lands.
    useEffect(() => { if (seed && !status) setStatus(seed) }, [seed, status])

    useEffect(() => {
      load()
      // Not while the keyboard is up: a refresh under it reorders the list and
      // the network being joined moves out from under the passphrase.
      const t = setInterval(() => { if (!asking && !busy) load() }, REFRESH_MS)
      return () => clearInterval(t)
    }, [asking, busy])

    const join = (n, password = '') => {
      setBusy(true); setMsg('')
      sdk.api.wifi.connect(n.ssid, password)
        .then((r) => {
          if (r.ok) { setMsg(`Connected to ${n.ssid}.`); load() }
          else setMsg(r.wrong_password ? 'Wrong password — try again'
                                       : (r.error || 'Could not join that network.'))
        })
        .catch(() => setMsg('Could not reach the backend.'))
        .finally(() => setBusy(false))
    }

    const activate = (n) => {
      if (!n || busy) return
      if (n.connected) {
        setBusy(true); setMsg('')
        sdk.api.wifi.disconnect()
          .then((r) => { setMsg(r.ok ? `Disconnected from ${n.ssid}.`
                                     : (r.error || 'Could not disconnect.')); load() })
          .catch(() => setMsg('Could not reach the backend.'))
          .finally(() => setBusy(false))
        return
      }
      if (n.secured) { setAskSeq((k) => k + 1); setAsking(n.ssid); return }
      join(n)
    }

    useEffect(() => {
      if (!active || asking) return   // the keyboard brings its own bindings
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move')
          setSel((i) => (i - 1 + Math.max(1, netsRef.current.length)) % Math.max(1, netsRef.current.length))
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move')
          setSel((i) => (i + 1) % Math.max(1, netsRef.current.length))
        }),
        sdk.input.onGp('gp:dpad-left', onLeave),
        sdk.input.onGp('gp:confirm', () => activate(netsRef.current[selRef.current])),
        sdk.input.onGp('gp:back', onLeave),
      ]
      return () => offs.forEach((off) => off())
    }, [active, asking, onLeave, busy])

    const cur = nets[sel] || nets[0] || null
    const curDetail = cur ? (detail[cur.ssid] || {}) : {}
    const isConn = !!(cur && cur.connected)
    const wired = !!(status && status.ethernet && status.ethernet.connected)

    // Only rows with a value. A blank "Gateway" reads as "this network has
    // none", which is a different and wrong statement.
    const rows = cur ? (isConn
      ? [
          ['Status', 'Connected'],
          ['IP address', status && status.ip],
          ['Gateway', status && status.gateway],
          ['DNS', status && (status.dns || []).join(', ')],
          ['Security', curDetail.security || (cur.secured ? 'Secured' : 'Open')],
          ['Signal', `${cur.signal}%`],
          ['Link rate', curDetail.rate],
          ['MAC address', status && status.mac],
        ]
      : [
          ['Status', 'Not connected'],
          ['Security', curDetail.security || (cur.secured ? 'Secured' : 'Open')],
          ['Band', curDetail.band],
          ['Channel', curDetail.channel ? String(curDetail.channel) : ''],
          ['Signal', `${cur.signal}%`],
          ['Link rate', curDetail.rate],
          ['Password', cur.secured ? 'Required' : 'Not required'],
        ]).filter(([, v]) => v) : []

    // A fragment, not three siblings: htm returns an array for multiple roots
    // and React then wants a key on each, which is a warning about a list this
    // is not — the three are the middle column, the detail column and a modal.
    return html`
      <${Fragment}>
      <section class="gcs-set-main" data-zone=${active ? 'on' : 'off'}>
        <div class="gcs-set-h-row">
          <div class="gcs-set-h">Wi-Fi</div>
          <div class="gcs-wifi-state">${wired ? 'WIRED' : loaded ? 'ON' : ''}</div>
        </div>
        <p class="gcs-set-sub">
          ${wired
            ? 'This box is on a cable. Wi-Fi stays available, and joining a network here does not unplug it.'
            : !loaded
              ? 'Selecting a network shows its details on the right; joining a secured network asks for its password.'
              // Only once the scan has answered may this screen say how many
              // networks there are. It used to read the length of an
              // as-yet-unfetched list, so the first thing on screen was "No
              // networks are in range" — on a box that was connected to one.
              : `${nets.length || 'No'} network${nets.length === 1 ? '' : 's'} ${nets.length === 1 ? 'is' : 'are'} in range. Selecting one shows its details on the right; joining a secured network asks for its password.`}
        </p>

        ${msg ? html`<div class="gcs-wifi-msg">${msg}</div>` : null}

        ${!loaded
          ? html`<div class="gcs-load"><i></i>${slow
              ? 'Still scanning — the radio is taking its time.' : 'Scanning for networks…'}</div>`
          : nets.length === 0
          ? html`<div class="gcs-wifi-empty">No network is in range.</div>`
          : nets.map((n, i) => {
            const d = detail[n.ssid] || {}
            const bars = barsFor(n.signal)
            const sub = [d.band, d.channel ? `channel ${d.channel}` : '', `${n.signal}%`]
              .filter(Boolean).join(' · ')
            return html`
              <div key=${n.ssid} class="gcs-wifi-row"
                   data-on=${active && i === sel ? '1' : '0'}
                   data-sel=${i === sel ? '1' : '0'}
                   onClick=${() => { setSel(i); activate(n) }}>
                <span class="gcs-wifi-bars">
                  ${[1, 2, 3, 4].map((k) => html`
                    <i key=${k} data-fill=${k <= bars ? '1' : '0'} style=${{ height: `${k * 25}%` }} />`)}
                </span>
                <span class="gcs-wifi-name">
                  <b>${n.ssid}</b>
                  <i>${sub}</i>
                </span>
                <span class="gcs-wifi-sec">${d.security || (n.secured ? 'Secured' : 'Open')}</span>
                ${n.connected ? html`<span class="gcs-wifi-conn">CONNECTED</span>` : null}
              </div>`
          })}

        ${loaded ? html`
          <div class="gcs-wifi-scan"><i></i>${busy ? 'WORKING' : 'SCANNING'}</div>` : null}
      </section>

      <aside class="gcs-set-aside">
        ${cur ? html`
          <div class="gcs-set-kicker">${isConn ? 'Active network' : 'Selected network'}</div>
          <div class="gcs-set-aside-title">${cur.ssid}</div>
          <dl class="gcs-set-facts">
            ${rows.map(([k, v]) => html`
              <div key=${k} class="gcs-set-fact"><dt>${k}</dt><dd>${v}</dd></div>`)}
          </dl>
          <button class="gcs-set-cta" disabled=${busy}
                  onClick=${() => activate(cur)}>
            ${isConn ? 'Disconnect' : 'Connect'}
          </button>` : null}
      </aside>

      ${asking ? html`
        <div class="gcs-set-dialog-scrim">
          <div class="gcs-set-dialog">
            <div class="gcs-set-kicker">Secured network</div>
            <div class="gcs-set-dialog-title">${asking}</div>
            <p class="gcs-set-sub">Enter the password to join this network.</p>
            <!-- The keyboard is the host's, and it draws itself in hardcoded
                 white on a black field — see VirtualKeyboard.tsx, where only the
                 accent is a variable. On a light dialog that is a keyboard you
                 cannot read, which is exactly what Shelf shipped. It gets its
                 own dark surface here rather than each theme discovering the
                 problem, and a theme whose dialog is already dark can make this
                 transparent in one rule. -->
            <div class="gcs-set-kb">
            <${Keyboard} key=${`${asking}-${askSeq}`}
              title="" password=${true} placeholder="Password"
              onConfirm=${(pw) => {
                const n = netsRef.current.find((x) => x.ssid === asking)
                setAsking(null)
                if (n) join(n, pw)
              }}
              onCancel=${() => setAsking(null)} />
            </div>
          </div>
        </div>` : null}
      <//>`
  }
}
