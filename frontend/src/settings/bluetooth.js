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
 * Orbit and Shelf pass `detail` and get one vertical list instead, because a
 * single column is the only shape where ↑↓ reaches everything:
 *
 *   · `detail="dialog"` (Orbit): paired devices, then what is in range, then a
 *     scan button. Each paired device is one row, and ✕ opens its dialog.
 *   · `detail="inline"` (Shelf): ONE list — the paired devices, then whatever
 *     a search found, marked New — under a "Search for devices" button. It does
 *     not search on its own: the owner presses the button when there is
 *     something to add. Each row is one stop: ✕ connects, disconnects or pairs;
 *     → reaches a paired device's small Forget button, ← comes back. (It was two
 *     lists, the search first, and before that the search sat under one
 *     two-button card per device, ten presses down on a box with five pads.)
 *
 * **Unpair and forget** is `DELETE /devices/{mac}`, which disconnects, removes
 * the pairing in BlueZ and reads the paired list back before it says yes. The
 * screen never hides a device on its own: the list is reloaded from the
 * adapter, and (except on Shelf, which only searches when asked) a fresh scan
 * runs so the device can be paired again from here. It always asks first, with
 * the cursor on Cancel.
 */
// What the adapter is told to do, mirrored from SCAN_SECS in the router so the
// screen can say how long it will be instead of just spinning.
const SCAN_SECS = 10
const SCAN_PATIENCE_MS = (SCAN_SECS + 4) * 1000

// BlueZ names a device that never said what it is after its own address,
// written either way round (`7C:ED:…` or `7C-ED-…`).
const MAC_NAME = /^([0-9A-F]{2}[-:]){5}[0-9A-F]{2}$/i
const nameless = (d) => !d.name || MAC_NAME.test(String(d.name).trim())

import { asList } from './list.js'
import { createDialogs } from './dialog.js'

export const createBluetoothPage = (sdk, useSlow, OwnDialog) => {
  // A page built on its own, outside the screen, still gets a working dialog.
  const Dialog = OwnDialog || createDialogs(sdk).Dialog
  const { html, useState, useEffect, useRef, React } = sdk.ui
  const Fragment = React.Fragment

  /** What both layouts need from the adapter, and the calls that change it. */
  /**
   * `autoScan` false (Shelf) means the adapter only searches when asked: no
   * search on arrival, none after a device is forgotten. A search keeps the
   * radio in discovery for ten seconds, which slows every connection meant
   * for a pad already paired — and most visits here are for those.
   */
  const useBluetooth = (seed, { autoScan = true } = {}) => {
    // Seeded from the rail. The settings screen already fetched the paired list
    // to put "2 connected" at the end of this row, so the page opens with it
    // rather than fetching the same thing again and showing an empty card while
    // it waits.
    const [paired, setPaired] = useState(() => seed || [])
    const [gotPaired, setGotPaired] = useState(() => !!seed)
    const [nearby, setNearby] = useState([])
    const [scanning, setScanning] = useState(false)
    // Whether a search has run at all. "Nothing found" and "never looked" are
    // different sentences, and only one of them is true on arrival.
    const [searched, setSearched] = useState(false)
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
        .finally(() => {
          scanningRef.current = false
          if (alive.current) { setScanning(false); setSearched(true) }
        })
    }

    // One scan on arrival. It blocks for SCAN_SECS on the other end, so it is
    // not on a timer: re-running it every few seconds would keep the adapter
    // permanently in discovery and make connecting to anything slower.
    useEffect(() => { if (autoScan) rescan(true) }, [])

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
          if (autoScan) rescan(true)
        })
    }

    return { paired, gotPaired, nearby, scanning, searched, busy, msg, rescan, act, forget }
  }

  /**
   * A cursor over a list of stops that can change under it.
   *
   * A key per stop so the cursor stays on the same device when the list is
   * reloaded; and a stop that vanished (the device just forgotten, a nearby pad
   * just paired) hands the cursor to whatever now occupies its place, rather
   * than throwing it back to the top of the page.
   */
  const useCursor = (stops, active) => {
    const [focusKey, setFocusKey] = useState(null)
    const at = Math.max(0, stops.findIndex((s) => s.key === focusKey))
    const lastAt = useRef(at)
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

    const setRef = (key) => (el) => { refs.current[key] = el }
    return { at, setFocusKey, ref, setRef }
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

  // ── one column, a dialog per device: Orbit ───────────────────────────────
  const Stacked = ({ active, onLeave, onLeft, seed }) => {
    const { paired, gotPaired, nearby, scanning, busy, msg, rescan, act, forget } = useBluetooth(seed)
    const slowPaired = useSlow(!gotPaired, 2500)
    const slowScan = useSlow(scanning, SCAN_PATIENCE_MS)
    // The paired device whose dialog is up, and the one waiting on
    // "Unpair and forget?". MACs, not objects: the list is reloaded
    // under both, and a stale object would describe a connection that ended.
    const [viewing, setViewing] = useState(null)
    const [forgetting, setForgetting] = useState(null)

    // Every stop the cursor can land on, in reading order.
    const stops = []
    for (const d of paired) stops.push({ key: `device:${d.mac}`, kind: 'device', d })
    for (const d of nearby) stops.push({ key: `pair:${d.mac}`, kind: 'pair', d })
    stops.push({ key: 'scan', kind: 'scan' })
    const { at, setFocusKey, ref, setRef } = useCursor(stops, active)

    const fire = (s) => {
      if (!s) return
      if (s.kind === 'scan') { rescan(); return }
      if (s.kind === 'pair') { act(s.d, 'pair'); return }
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
          Select a device to connect, disconnect or forget it. Controllers reconnect on their own when the console wakes.
        </p>

        ${msg ? html`<div class="gcs-wifi-msg" role="status">${msg}</div>` : null}

        <div class="gcs-set-kicker gcs-row2-head">Paired devices</div>
        ${!gotPaired
          ? html`<div class="gcs-load"><i></i>${slowPaired
              ? 'Still asking the adapter…' : 'Reading the paired list…'}</div>`
          : paired.length === 0
            ? html`<div class="gcs-wifi-empty">Nothing is paired yet.</div>`
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

  // ── one list, search on demand: Shelf ────────────────────────────────────
  const Inline = ({ active, onLeave, onLeft, seed }) => {
    const { paired, gotPaired, nearby, scanning, searched, busy, msg, rescan, act, forget } =
      useBluetooth(seed, { autoScan: false })
    const slowPaired = useSlow(!gotPaired, 2500)
    const slowScan = useSlow(scanning, SCAN_PATIENCE_MS)
    const [forgetting, setForgetting] = useState(null)
    // Which of a paired row's two buttons the cursor is on: 0 the main action,
    // 1 Forget. Reset by every ↑↓, so a row is always entered on the safe one.
    const [side, setSide] = useState(0)

    // A device that advertises no name shows up as its own address. It is still
    // listed — it may be the pad being paired, before it has said what it is —
    // but after everything that did introduce itself.
    const found = nearby.map((d, i) => ({ d, i, anon: nameless(d) }))
      .sort((a, b) => (a.anon - b.anon) || (a.i - b.i)).map((x) => x.d)

    const stops = [{ key: 'scan', kind: 'scan' }]
    for (const d of paired) stops.push({ key: `mine:${d.mac}`, kind: 'mine', d })
    for (const d of found) stops.push({ key: `pair:${d.mac}`, kind: 'pair', d })
    const { at, setFocusKey, ref, setRef } = useCursor(stops, active)

    const sideRef = useRef(side)
    useEffect(() => { sideRef.current = side }, [side])

    // A search the owner started from the button, which is where the cursor
    // still is, ends on its first result: that is the row they are about to
    // press. A cursor they have since moved is left where they put it.
    // Flagged when the search is asked for rather than inferred from
    // `scanning` going true then false: a fast answer can land in the same
    // render as the request, and the true would never be seen.
    const jump = useRef(false)
    useEffect(() => {
      if (!jump.current || scanning) return
      jump.current = false
      const { stops: now, at: i } = ref.current
      if (found.length && now[i] && now[i].key === 'scan') setFocusKey(`pair:${found[0].mac}`)
    }, [scanning, nearby])

    const fire = (s, which) => {
      if (!s) return
      if (s.kind === 'scan') { if (!scanning) { jump.current = true; rescan() } return }
      if (s.kind === 'pair') { act(s.d, 'pair'); return }
      if (which === 1) setForgetting(s.d.mac)
      else act(s.d, 'toggle')
    }

    const open = !!forgetting
    useEffect(() => {
      if (!active || open) return
      const len = () => Math.max(1, ref.current.stops.length)
      const cur = () => ref.current.stops[ref.current.at]
      const move = (d) => {
        sdk.system.playSound('move')
        const s = ref.current.stops[(ref.current.at + d + len()) % len()]
        setSide(0)
        if (s) setFocusKey(s.key)
      }
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => move(-1)),
        sdk.input.onGp('gp:dpad-down', () => move(1)),
        sdk.input.onGp('gp:dpad-right', () => {
          const s = cur()
          if (s && s.kind === 'mine' && sideRef.current === 0) { sdk.system.playSound('move'); setSide(1) }
        }),
        // ← steps back off Forget first; only from a row's main button does it
        // leave the page for the rail, which is what it does everywhere else.
        sdk.input.onGp('gp:dpad-left', () => {
          const s = cur()
          if (s && s.kind === 'mine' && sideRef.current === 1) { sdk.system.playSound('move'); setSide(0); return }
          ;(onLeft || onLeave)()
        }),
        sdk.input.onGp('gp:confirm', () => {
          sdk.system.playSound('confirm')
          fire(cur(), sideRef.current)
        }),
        sdk.input.onGp('gp:back', onLeave),
      ]
      return () => offs.forEach((off) => off())
    }, [active, open, onLeave, busy, scanning])

    const on = (key, which = 0) => active && !open && stops[at] && stops[at].key === key
      && (!key.startsWith('mine:') || side === which)
    const click = (key, which = 0) => (e) => {
      if (e) e.stopPropagation()
      setFocusKey(key); setSide(which)
      fire(stops.find((x) => x.key === key), which)
    }

    const doomed = forgetting && paired.find((d) => d.mac === forgetting)
    useEffect(() => {
      if (gotPaired && forgetting && !doomed) setForgetting(null)
    }, [gotPaired, forgetting, doomed])

    const connected = paired.filter((d) => d.connected).length
    const here = stops[at]
    const focusedRow = (key) => here && here.key === key && active && !open

    const status = scanning
      ? (slowScan ? 'Still looking — some devices only advertise every few seconds.'
                  : `Searching for ${SCAN_SECS} seconds — put the device in pairing mode.`)
      : searched
        ? (found.length
            ? `${found.length} new device${found.length > 1 ? 's' : ''} found — listed below.`
            : 'No new device found. Check it is in pairing mode, then search again.')
        : 'Put the controller or headset in pairing mode first.'

    return html`
      <${Fragment}>
      <section class="gcs-set-main gcs-bt-shelf" data-zone=${active ? 'on' : 'off'}>
        <div class="gcs-set-h-row">
          <div class="gcs-set-h">Bluetooth</div>
          <div class="gcs-wifi-state">${gotPaired ? `${connected} CONNECTED` : ''}</div>
        </div>

        ${msg ? html`<div class="gcs-wifi-msg" role="status">${msg}</div>` : null}

        <div class="gcs-bt-search" data-scanning=${scanning ? '1' : '0'}>
          <button type="button" class="gcs-bt-act gcs-bt-scan" data-primary="1" ref=${setRef('scan')}
                  data-on=${on('scan') ? '1' : '0'} disabled=${scanning}
                  onClick=${click('scan')}>
            ${scanning ? 'Searching…' : searched ? 'Search again' : 'Search for devices'}
          </button>
          <span class="gcs-bt-search-say" role="status">${status}</span>
          ${scanning ? html`<div class="gcs-bt-sweep" aria-hidden="true"><i></i></div>` : null}
        </div>

        <div class="gcs-set-kicker gcs-row2-head">
          Devices${gotPaired && (paired.length || found.length)
            ? ` · ${paired.length + found.length}` : ''}
        </div>
        ${!gotPaired
          ? html`<div class="gcs-load"><i></i>${slowPaired
              ? 'Still asking the adapter…' : 'Reading the paired list…'}</div>`
          : paired.length === 0 && found.length === 0
            ? html`<div class="gcs-wifi-empty">No device yet. Press Search for devices to add one.</div>`
            : null}

        ${paired.map((d) => {
          const key = `mine:${d.mac}`
          const focused = focusedRow(key)
          const working = busy === d.mac
          return html`
            <div key=${d.mac} class="gcs-bt-mine" ref=${setRef(key)}
                 aria-label=${`${d.name}, ${d.connected ? 'connected' : 'not connected'}`}
                 data-live=${d.connected ? '1' : '0'} data-here=${focused ? '1' : '0'}>
              <span class="gcs-bt-dot" data-live=${d.connected ? '1' : '0'}></span>
              <span class="gcs-bt-name">
                <b>${d.name}</b>
                <i>${working ? 'Working…' : d.connected ? 'Connected' : 'Not connected'}${
                  focused ? html`<span class="gcs-bt-mac"> · ${d.mac}</span>` : null}</i>
              </span>
              <button type="button" class="gcs-bt-act" data-primary=${d.connected ? '0' : '1'}
                      data-on=${on(key, 0) ? '1' : '0'} disabled=${!!busy}
                      onClick=${click(key, 0)}>
                ${d.connected ? 'Disconnect' : 'Connect'}
              </button>
              <button type="button" class="gcs-bt-act gcs-bt-forget" data-danger="1"
                      data-on=${on(key, 1) ? '1' : '0'} disabled=${!!busy}
                      onClick=${click(key, 1)}>
                Forget
              </button>
            </div>`
        })}

        ${found.map((d) => {
          const key = `pair:${d.mac}`
          const anon = nameless(d)
          const focused = focusedRow(key)
          return html`
            <div key=${d.mac} class="gcs-bt-mine gcs-bt-new" ref=${setRef(key)}
                 aria-label=${`New device: ${anon ? 'unnamed, ' + d.mac : d.name}`}
                 data-anon=${anon ? '1' : '0'} data-here=${focused ? '1' : '0'}>
              <span class="gcs-bt-tag">NEW</span>
              <span class="gcs-bt-name">
                <b>${anon ? 'Unnamed device' : d.name}</b>
                <i>${busy === d.mac ? 'Pairing…' : 'Not paired yet'}${
                  focused || anon ? html`<span class="gcs-bt-mac"> · ${d.mac}</span>` : null}</i>
              </span>
              <button type="button" class="gcs-bt-act" data-primary="1"
                      data-on=${on(key) ? '1' : '0'} disabled=${!!busy}
                      onClick=${click(key)}>
                ${busy === d.mac ? 'Pairing…' : 'Pair'}
              </button>
            </div>`
        })}

        <p class="gcs-bt-foot">
          ✕ connects, disconnects or pairs · → then ✕ forgets a device. Controllers reconnect on their own when the console wakes.
        </p>
      </section>

      ${doomed ? html`
        <${Dialog}
          kicker="Bluetooth"
          title=${`Unpair and forget ${doomed.name}?`}
          body="The device will be disconnected and removed from your devices. Pair it again to reconnect."
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

  return (props) => (props.detail === 'inline'
    ? html`<${Inline} ...${props} />`
    : props.detail
      ? html`<${Stacked} ...${props} />`
      : html`<${Columns} ...${props} />`)
}
