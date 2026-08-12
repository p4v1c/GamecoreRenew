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
 * screen: who is paired, who is connected, what is in range, and the two
 * buttons that change either.
 */
// What the adapter is told to do, mirrored from SCAN_SECS in the router so the
// screen can say how long it will be instead of just spinning.
const SCAN_SECS = 10
const SCAN_PATIENCE_MS = (SCAN_SECS + 4) * 1000

import { asList } from './list.js'

export const createBluetoothPage = (sdk, useSlow) => {
  const { html, useState, useEffect, useRef, React } = sdk.ui
  const Fragment = React.Fragment

  return ({ active, onLeave, seed }) => {
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

    const loadPaired = () => sdk.api.bluetooth.devices()
      .then((r) => setPaired(asList(r)))
      .catch(() => {})
      // Loaded means "the question has been answered", including answered
      // badly. An adapter that is off has no paired devices and no error to
      // show; leaving this false would spin for ever on a box with no radio.
      .finally(() => setGotPaired(true))

    // The seed can arrive AFTER this page has mounted — the rail's requests and
    // a player pressing straight down to Bluetooth are in a race, and the seed
    // loses it whenever the box is slow, which is exactly when it matters.
    // Adopted whenever it turns up, until the page's own answer supersedes it.
    useEffect(() => {
      if (seed && !gotPaired) { setPaired(seed); setGotPaired(true) }
    }, [seed, gotPaired])

    useEffect(() => { loadPaired() }, [])

    // One scan on arrival. It blocks for SCAN_SECS on the other end, so it is
    // not on a timer: re-running it every few seconds would keep the adapter
    // permanently in discovery and make connecting to anything slower.
    useEffect(() => {
      let alive = true
      setScanning(true)
      sdk.api.bluetooth.scan()
        .then((r) => { if (alive) setNearby(r.found || []) })
        .catch(() => {})
        .finally(() => { if (alive) setScanning(false) })
      return () => { alive = false }
    }, [])

    const rescan = () => {
      if (scanning) return
      setScanning(true); setMsg('')
      sdk.api.bluetooth.scan()
        .then((r) => setNearby(asList(r && r.found)))
        .catch(() => setMsg('Could not scan.'))
        .finally(() => setScanning(false))
    }

    const act = (d, kind) => {
      if (busy) return
      setBusy(d.mac); setMsg('')
      const done = (m) => { setMsg(m); loadPaired(); setBusy('') }
      if (kind === 'pair') {
        sdk.api.bluetooth.pair(d.mac)
          .then((r) => {
            // Paired-but-not-connected is a real, useful state and the router
            // says so rather than calling it a failure. Echo its words.
            if (r.ok) setNearby((n) => n.filter((x) => x.mac !== d.mac))
            done(r.message || (r.ok ? 'Paired.' : 'Pairing failed.'))
          })
          .catch(() => done('Could not reach the backend.'))
        return
      }
      const call = d.connected ? sdk.api.bluetooth.disconnect(d.mac)
                               : sdk.api.bluetooth.connect(d.mac)
      call.then((r) => done(r.message || (r.ok ? 'Done.' : 'Failed.')))
          .catch(() => done('Could not reach the backend.'))
    }

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
          else onLeave()
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
              <span class="gcs-wifi-scan" onClick=${rescan}>
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
}
