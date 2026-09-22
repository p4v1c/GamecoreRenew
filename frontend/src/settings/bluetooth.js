/**
 * Settings → Bluetooth.
 *
 * One card, two columns inside it — Paired on the left, Nearby on the right —
 * the way the capture draws it. Not a third top-level column like Wi-Fi's
 * detail panel: these are two lists of the same kind of thing, and the capture
 * treats them as one surface.
 *
 * Bare markup. Pairing, trusting and connecting stay in the host's router,
 * which does them in the one order that is safe (`pair`, then `trust`, then
 * `connect` — trusting an unpaired address tells BlueZ to accept a future
 * connection from something that has not proved who it is).
 *
 * ## Where this departs from the capture, and why
 *
 * · **No ON/OFF switch.** Same as Wi-Fi: no route turns the adapter off.
 * · **No battery bar per device.** `GET /devices` answers
 *   `{mac, name, connected, paired}` and nothing else. Battery levels do exist
 *   in `sysinfo.controllers`, but that list carries no MAC — matching a pad to
 *   a Bluetooth address by NAME would be a guess, and a wrong guess here reads
 *   as the box confusing player one with player two. Two lists that cannot be
 *   joined are better left unjoined than joined by hope.
 * · **No RSSI.** `-54 dBm` in the capture has no source: the scan reports what
 *   BlueZ remembers seeing, not how loudly.
 * · **No device-class tags** (PAD / AUD / KBD). Nothing reports a class.
 *
 * What remains is what the box can actually answer, and it is most of the
 * screen: who is paired, who is connected, what is in range, and the buttons
 * that change either.
 *
 * ## Two layouts
 *
 * The two columns above are what the built-in UI and Summer draw, unchanged.
 * Orbit and Shelf pass `detail` and get one vertical list instead — paired
 * devices, then what is in range, then a scan button — because a single column
 * is the only shape where ↑↓ reaches everything and ←→ is left free:
 *
 *   · `detail="inline"` (Shelf): each paired device is a card carrying its own
 *     two buttons, Connect/Disconnect and Unpair and forget.
 *   · `detail="dialog"` (Orbit): each paired device is one row, and ✕ opens its
 *     dialog with the same two actions.
 *
 * **Unpair and forget** is `DELETE /devices/{mac}`, which disconnects, removes
 * the pairing in BlueZ and reads the paired list back before it says yes. The
 * screen never hides a device on its own: the list is reloaded from the
 * adapter, and a fresh scan runs so the device can be paired again from here.
 * It always asks first, with the cursor on Cancel.
 */
// What the adapter is told to do, mirrored from SCAN_SECS in the router so the
// screen can say how long it will be instead of just spinning.
const SCAN_SECS = 10
const SCAN_PATIENCE_MS = (SCAN_SECS + 4) * 1000

import { asList } from './list.js'
import { createDialogs } from './dialog.js'

export const createBluetoothPage = (sdk, useSlow, OwnDialog) => {
  // A page built on its own, outside the screen, still gets a working dialog.
  const Dialog = OwnDialog || createDialogs(sdk).Dialog
  const { html, useState, useEffect, useRef, React } = sdk.ui
  const Fragment = React.Fragment

  /** What both layouts need from the adapter, and the calls that change it. */
  const useBluetooth = (seed) => {
    // Seeded from the rail. The settings screen already fetched the paired list
    // to put "2 connected" at the end of this row, so the page opens with it
    // rather than fetching the same thing again and showing an empty card while
    // it waits.
    const [paired, setPaired] = useState(() => seed || [])
    const [gotPaired, setGotPaired] = useState(() => !!seed)
    const [nearby, setNearby] = useState([])
    const [scanning, setScanning] = useState(false)
    const [busy, setBusy] = useState('')      // mac being worked on
    const [msg, setMsg] = useState('')
    const alive = useRef(true)
    useEffect(() => () => { alive.current = false }, [])

    const loadPaired = () => sdk.api.bluetooth.devices()
      .then((r) => { if (alive.current) setPaired(asList(r)) })
      .catch(() => {})
      // Loaded means "the question has been answered", including answered
      // badly. An adapter that is off has no paired devices and no error to
      // show; leaving this false would spin for ever on a box with no radio.
      .finally(() => { if (alive.current) setGotPaired(true) })

    // The seed can arrive AFTER this page has mounted — the rail's requests and
    // a player pressing straight down to Bluetooth are in a race, and the seed
    // loses it whenever the box is slow, which is exactly when it matters.
    // Adopted whenever it turns up, until the page's own answer supersedes it.
    useEffect(() => {
      if (seed && !gotPaired) { setPaired(seed); setGotPaired(true) }
    }, [seed, gotPaired])

    useEffect(() => { loadPaired() }, [])

    const scanningRef = useRef(false)
    const rescan = (quiet = false) => {
      if (scanningRef.current) return
      scanningRef.current = true
      setScanning(true); if (!quiet) setMsg('')
      sdk.api.bluetooth.scan()
        .then((r) => { if (alive.current) setNearby(asList(r && r.found)) })
        .catch(() => { if (alive.current && !quiet) setMsg('Could not scan.') })
        .finally(() => { scanningRef.current = false; if (alive.current) setScanning(false) })
    }

    // One scan on arrival. It blocks for SCAN_SECS on the other end, so it is
    // not on a timer: re-running it every few seconds would keep the adapter
    // permanently in discovery and make connecting to anything slower.
    useEffect(() => { rescan(true) }, [])

    const act = (d, kind) => {
      if (busy) return
      setBusy(d.mac); setMsg('')
      const done = (m) => { if (!alive.current) return; setMsg(m); loadPaired(); setBusy('') }
      if (kind === 'pair') {
        sdk.api.bluetooth.pair(d.mac)
          .then((r) => {
            // Paired-but-not-connected is a real, useful state and the router
            // says so rather than calling it a failure. Echo its words.
            if (r.ok && alive.current) setNearby((n) => n.filter((x) => x.mac !== d.mac))
            done(r.message || (r.ok ? 'Paired.' : 'Pairing failed.'))
          })
          .catch(() => done('Could not reach the backend.'))
        return
      }
      const call = d.connected ? sdk.api.bluetooth.disconnect(d.mac)
                               : sdk.api.bluetooth.connect(d.mac)
      call.then((r) => done(r.message || (r.ok
            ? (d.connected ? `${d.name} disconnected — it stays paired.` : `${d.name} connected.`)
            : 'Failed.')))
          .catch(() => done('Could not reach the backend.'))
    }

    // Unpair and forget. The list is reloaded from the adapter either way, so
    // what the screen shows afterwards is BlueZ's answer, never this page's
    // guess; and a scan follows, so a device that is still awake shows up
    // under Nearby, ready to pair again.
    const forget = (d) => {
      if (busy) return
      setBusy(d.mac); setMsg('')
      sdk.api.bluetooth.remove(d.mac)
        .then((r) => {
          if (!alive.current) return
          setMsg(r && r.ok ? `${d.name} forgotten. Pair it again to reconnect.`
                           : ((r && r.message) || `${d.name} is still paired.`))
        })
        .catch(() => { if (alive.current) setMsg('Could not reach the backend.') })
        .finally(() => {
          if (!alive.current) return
          setBusy('')
          loadPaired()
          rescan(true)
        })
    }

    return { paired, gotPaired, nearby, scanning, busy, msg, rescan, act, forget }
  }

  // ── the two columns: the built-in UI and Summer ──────────────────────────
  const Columns = ({ active, onLeave, onLeft, seed }) => {
    const { paired, gotPaired, nearby, scanning, busy, msg, rescan, act } = useBluetooth(seed)
    const [col, setCol] = useState('paired')
    const [idx, setIdx] = useState(0)
    // Nothing is wrong yet — it is just taking a while. The scan is ten seconds
    // by design, so its patience is longer than the paired list's; a "still
    // working" that fires during a normal scan would be crying wolf.
    const slowPaired = useSlow(!gotPaired, 2500)
    const slowScan = useSlow(scanning, SCAN_PATIENCE_MS)

    const stateRef = useRef({ col, idx, paired, nearby })
    useEffect(() => { stateRef.current = { col, idx, paired, nearby } },
      [col, idx, paired, nearby])

    useEffect(() => {
      if (!active) return
      const len = (c) => Math.max(1, (c === 'paired' ? stateRef.current.paired
                                                     : stateRef.current.nearby).length)
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move')
          setIdx((i) => (i - 1 + len(stateRef.current.col)) % len(stateRef.current.col))
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move')
          setIdx((i) => (i + 1) % len(stateRef.current.col))
        }),
        // Left out of the Paired column is the way back to the rail; left out
        // of Nearby only crosses to Paired. One button, two meanings, decided
        // by where you already are — which is how every column UI on a pad works.
        sdk.input.onGp('gp:dpad-left', () => {
          if (stateRef.current.col === 'nearby') { sdk.system.playSound('move'); setCol('paired'); setIdx(0) }
          else (onLeft || onLeave)()
        }),
        sdk.input.onGp('gp:dpad-right', () => {
          if (stateRef.current.col === 'paired' && stateRef.current.nearby.length) {
            sdk.system.playSound('move'); setCol('nearby'); setIdx(0)
          }
        }),
        sdk.input.onGp('gp:confirm', () => {
          const s = stateRef.current
          const d = (s.col === 'paired' ? s.paired : s.nearby)[s.idx]
          if (d) act(d, s.col === 'paired' ? 'toggle' : 'pair')
        }),
        sdk.input.onGp('gp:back', onLeave),
      ]
      return () => offs.forEach((off) => off())
    }, [active, onLeave, busy, scanning])

    const row = (d, i, kind) => {
      const on = active && col === kind && idx === i
      const working = busy === d.mac
      return html`
        <div key=${d.mac} class="gcs-bt-row" data-on=${on ? '1' : '0'}
             onClick=${() => { setCol(kind); setIdx(i); act(d, kind === 'paired' ? 'toggle' : 'pair') }}>
          <span class="gcs-bt-dot" data-live=${d.connected ? '1' : '0'}></span>
          <span class="gcs-bt-name">
            <b>${d.name}</b>
            <i>${d.mac}</i>
          </span>
          ${kind === 'paired'
            ? html`<span class="gcs-bt-state" data-live=${d.connected ? '1' : '0'}>
                     ${working ? 'WORKING' : d.connected ? 'CONNECTED' : 'OFFLINE'}
                   </span>`
            : html`<span class="gcs-bt-btn">${working ? 'Pairing…' : 'Connect'}</span>`}
        </div>`
    }

    return html`
      <${Fragment}>
      <section class="gcs-set-main" data-zone=${active ? 'on' : 'off'}>
        <div class="gcs-set-h-row">
          <div class="gcs-set-h">Bluetooth</div>
          <div class="gcs-wifi-state">${paired.some((d) => d.connected) ? 'ON' : ''}</div>
        </div>
        <p class="gcs-set-sub">
          Pairing keeps what you have already introduced to the box. Controllers
          reconnect on their own when the console wakes.
        </p>

        ${msg ? html`<div class="gcs-wifi-msg">${msg}</div>` : null}

        <div class="gcs-bt-cols">
          <div class="gcs-bt-col">
            <div class="gcs-set-kicker">Paired</div>
            ${!gotPaired
              ? html`<div class="gcs-load"><i></i>${slowPaired
                  ? 'Still asking the adapter…' : 'Reading the paired list…'}</div>`
              : paired.length === 0
                ? html`<div class="gcs-wifi-empty">Nothing is paired yet.</div>`
                : paired.map((d, i) => row(d, i, 'paired'))}
          </div>

          <div class="gcs-bt-col">
            <div class="gcs-bt-head">
              <span class="gcs-set-kicker">Nearby</span>
              <span class="gcs-wifi-scan" onClick=${() => rescan()}>
                <i data-idle=${scanning ? '0' : '1'}></i>${scanning ? 'SCANNING' : 'SCAN AGAIN'}
              </span>
            </div>
            ${nearby.length === 0
              ? (scanning
                  ? html`<div class="gcs-load"><i></i>${slowScan
                      ? 'Still looking — some devices only advertise every few seconds.'
                      : `Looking around for ${SCAN_SECS} seconds…`}</div>`
                  : html`<div class="gcs-wifi-empty">Nothing new in range.</div>`)
              : nearby.map((d, i) => row(d, i, 'nearby'))}
          </div>
        </div>
      </section>
      <//>`
  }

  // ── one column: Orbit (dialog) and Shelf (inline cards) ──────────────────
  const Stacked = ({ active, onLeave, onLeft, seed, detail }) => {
    const { paired, gotPaired, nearby, scanning, busy, msg, rescan, act, forget } = useBluetooth(seed)
    const cards = detail === 'inline'
    const slowPaired = useSlow(!gotPaired, 2500)
    const slowScan = useSlow(scanning, SCAN_PATIENCE_MS)
    // The paired device whose dialog is up (Orbit), and the one waiting on
    // "Unpair and forget?" (both). MACs, not objects: the list is reloaded
    // under both, and a stale object would describe a connection that ended.
    const [viewing, setViewing] = useState(null)
    const [forgetting, setForgetting] = useState(null)

    // Every stop the cursor can land on, in reading order. A key per stop so
    // the cursor stays on the same device when the list is reloaded under it.
    const stops = []
    for (const d of paired) {
      if (cards) {
        stops.push({ key: `toggle:${d.mac}`, kind: 'toggle', d })
        stops.push({ key: `forget:${d.mac}`, kind: 'forget', d })
      } else stops.push({ key: `device:${d.mac}`, kind: 'device', d })
    }
    for (const d of nearby) stops.push({ key: `pair:${d.mac}`, kind: 'pair', d })
    stops.push({ key: 'scan', kind: 'scan' })

    const [focusKey, setFocusKey] = useState(null)
    const at = Math.max(0, stops.findIndex((s) => s.key === focusKey))
    const lastAt = useRef(at)
    // A stop that vanished (the device just forgotten, a nearby pad just
    // paired) hands the cursor to whatever now occupies its place, rather than
    // throwing it back to the top of the page.
    useEffect(() => {
      if (focusKey && !stops.some((s) => s.key === focusKey)) {
        const next = stops[Math.min(lastAt.current, stops.length - 1)]
        setFocusKey(next ? next.key : null)
      } else lastAt.current = at
    })

    const ref = useRef({ stops, at })
    useEffect(() => { ref.current = { stops, at } })

    const refs = useRef({})
    useEffect(() => {
      const s = stops[at]
      if (active && s) refs.current[s.key]?.scrollIntoView?.({ block: 'nearest' })
    }, [at, active, stops.length])

    const fire = (s) => {
      if (!s) return
      if (s.kind === 'scan') { rescan(); return }
      if (s.kind === 'pair') { act(s.d, 'pair'); return }
      if (s.kind === 'toggle') { act(s.d, 'toggle'); return }
      if (s.kind === 'forget') { setForgetting(s.d.mac); return }
      if (s.kind === 'device') setViewing(s.d.mac)
    }

    const open = !!(viewing || forgetting)
    useEffect(() => {
      if (!active || open) return
      const len = () => Math.max(1, ref.current.stops.length)
      const move = (d) => {
        sdk.system.playSound('move')
        const i = (ref.current.at + d + len()) % len()
        const s = ref.current.stops[i]
        if (s) setFocusKey(s.key)
      }
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => move(-1)),
        sdk.input.onGp('gp:dpad-down', () => move(1)),
        sdk.input.onGp('gp:dpad-left', onLeft || onLeave),
        sdk.input.onGp('gp:confirm', () => {
          sdk.system.playSound('confirm')
          fire(ref.current.stops[ref.current.at])
        }),
        sdk.input.onGp('gp:back', onLeave),
      ]
      return () => offs.forEach((off) => off())
    }, [active, open, onLeave, busy, scanning])

    const on = (key) => active && !open && stops[at] && stops[at].key === key
    const setRef = (key) => (el) => { refs.current[key] = el }
    const click = (key) => () => {
      const s = stops.find((x) => x.key === key)
      setFocusKey(key); fire(s)
    }

    const shown = viewing && paired.find((d) => d.mac === viewing)
    const doomed = forgetting && paired.find((d) => d.mac === forgetting)
    // A dialog about a device that has left the paired list describes nothing.
    useEffect(() => {
      if (gotPaired && viewing && !shown) setViewing(null)
      if (gotPaired && forgetting && !doomed) setForgetting(null)
    }, [gotPaired, viewing, shown, forgetting, doomed])

    const connected = paired.filter((d) => d.connected).length

    return html`
      <${Fragment}>
      <section class="gcs-set-main gcs-bt-stack" data-zone=${active ? 'on' : 'off'}>
        <div class="gcs-set-h-row">
          <div class="gcs-set-h">Bluetooth</div>
          <div class="gcs-wifi-state">${gotPaired ? `${connected} CONNECTED` : ''}</div>
        </div>
        <p class="gcs-set-sub">
          ${cards
            ? 'Manage your devices, disconnect them or remove their pairing. Controllers reconnect on their own when the console wakes.'
            : 'Select a device to connect, disconnect or forget it. Controllers reconnect on their own when the console wakes.'}
        </p>

        ${msg ? html`<div class="gcs-wifi-msg" role="status">${msg}</div>` : null}

        <div class="gcs-set-kicker gcs-row2-head">Paired devices</div>
        ${!gotPaired
          ? html`<div class="gcs-load"><i></i>${slowPaired
              ? 'Still asking the adapter…' : 'Reading the paired list…'}</div>`
          : paired.length === 0
            ? html`<div class="gcs-wifi-empty">Nothing is paired yet.</div>`
            : cards
              ? html`<div class="gcs-bt-cards">
                  ${paired.map((d) => {
                    const working = busy === d.mac
                    return html`
                      <article key=${d.mac} class="gcs-bt-card" aria-label=${d.name}
                               data-live=${d.connected ? '1' : '0'}>
                        <div class="gcs-bt-card-head">
                          <span class="gcs-bt-name"><b>${d.name}</b><i>${d.mac}</i></span>
                          <span class="gcs-bt-chip" data-live=${d.connected ? '1' : '0'}>
                            ${working ? 'WORKING' : d.connected ? 'CONNECTED' : 'DISCONNECTED'}
                          </span>
                        </div>
                        <div class="gcs-bt-card-acts">
                          <button type="button" class="gcs-bt-act" ref=${setRef(`toggle:${d.mac}`)}
                                  data-on=${on(`toggle:${d.mac}`) ? '1' : '0'} disabled=${!!busy}
                                  onClick=${click(`toggle:${d.mac}`)}>
                            ${d.connected ? 'Disconnect' : 'Connect'}
                          </button>
                          <button type="button" class="gcs-bt-act" data-danger="1"
                                  ref=${setRef(`forget:${d.mac}`)}
                                  data-on=${on(`forget:${d.mac}`) ? '1' : '0'} disabled=${!!busy}
                                  onClick=${click(`forget:${d.mac}`)}>
                            Unpair and forget
                          </button>
                        </div>
                      </article>`
                  })}
                </div>`
              : paired.map((d) => html`
                  <div key=${d.mac} class="gcs-row2 gcs-bt-dev" role="button"
                       aria-label=${`${d.name}, ${d.connected ? 'connected' : 'disconnected'}`}
                       ref=${setRef(`device:${d.mac}`)}
                       data-on=${on(`device:${d.mac}`) ? '1' : '0'}
                       onClick=${click(`device:${d.mac}`)}>
                    <span class="gcs-bt-dot" data-live=${d.connected ? '1' : '0'}></span>
                    <span class="gcs-row2-text"><b>${d.name}</b><i>${d.mac}</i></span>
                    <span class="gcs-row2-info">
                      ${busy === d.mac ? 'Working…' : d.connected ? 'Connected' : 'Disconnected'}
                    </span>
                    <span class="gcs-set-chev" aria-hidden="true">›</span>
                  </div>`)}

        <div class="gcs-set-kicker gcs-row2-head">Nearby devices</div>
        ${nearby.length === 0
          ? (scanning
              ? html`<div class="gcs-load"><i></i>${slowScan
                  ? 'Still looking — some devices only advertise every few seconds.'
                  : `Looking around for ${SCAN_SECS} seconds…`}</div>`
              : html`<div class="gcs-wifi-empty">No new devices found.</div>`)
          : nearby.map((d) => html`
              <div key=${d.mac} class="gcs-row2 gcs-bt-near" role="button"
                   aria-label=${`Pair ${d.name}`}
                   ref=${setRef(`pair:${d.mac}`)}
                   data-on=${on(`pair:${d.mac}`) ? '1' : '0'}
                   onClick=${click(`pair:${d.mac}`)}>
                <span class="gcs-row2-text"><b>${d.name}</b><i>${d.mac}</i></span>
                <span class="gcs-act">${busy === d.mac ? 'Pairing…' : 'Pair'}</span>
              </div>`)}

        <div class="gcs-bt-scanrow">
          <button type="button" class="gcs-bt-act gcs-bt-scan" ref=${setRef('scan')}
                  data-on=${on('scan') ? '1' : '0'} disabled=${scanning}
                  onClick=${click('scan')}>
            ${scanning ? 'Scanning…' : 'Scan for devices'}
          </button>
        </div>
      </section>

      ${shown && !doomed ? html`
        <${Dialog}
          kicker="Paired device"
          title=${shown.name}
          body=${`${shown.mac} · ${busy === shown.mac ? 'Working…' : shown.connected ? 'Connected' : 'Disconnected'}`}
          onCancel=${() => setViewing(null)}
          actions=${[
            {
              id: 'toggle', disabled: !!busy,
              label: shown.connected ? 'Disconnect' : 'Connect',
              desc: 'The device stays paired',
              run: () => act(shown, 'toggle'),
            },
            {
              id: 'forget', danger: true, disabled: !!busy,
              label: 'Unpair and forget', desc: 'Remove this device’s pairing',
              run: () => { setViewing(null); setForgetting(shown.mac) },
            },
            { id: 'back', label: 'Back', run: () => setViewing(null) },
          ]} />` : null}

      ${doomed ? html`
        <${Dialog}
          kicker="Bluetooth"
          title=${`Unpair and forget ${doomed.name}?`}
          body="The device will be disconnected and removed from paired devices. Pair it again to reconnect."
          initial=${0}
          onCancel=${() => setForgetting(null)}
          actions=${[
            { id: 'cancel', label: 'Cancel', run: () => setForgetting(null) },
            {
              id: 'forget', danger: true, primary: true, label: 'Unpair and forget',
              run: () => { setForgetting(null); forget(doomed) },
            },
          ]} />` : null}
      <//>`
  }

  return (props) => (props.detail
    ? html`<${Stacked} ...${props} />`
    : html`<${Columns} ...${props} />`)
}
