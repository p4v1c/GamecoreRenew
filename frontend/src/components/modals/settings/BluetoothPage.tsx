import { useState, useEffect, useRef } from 'react'
import { Overlay, BackHeader } from '../../ui'
import { api, type BtDevice } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { useSubPageGamepad } from './useSubPageGamepad'
import { PadHints } from '../../../lib/padKey'

type BtOp = 'connect' | 'disconnect' | 'scan' | 'pair' | null

/**
 * Two lists, not one.
 *
 * `devices` is what the adapter already knows; `found` is what the last scan
 * saw and has never been paired. They were the same list before, because the
 * backend only ever returned paired devices — so the scan button ran for eight
 * seconds and could not, by construction, reveal anything new.
 *
 * The cursor walks them as one sequence: a player pressing down does not care
 * where our bookkeeping changes.
 */

export function BluetoothPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [devices, setDevices] = useState<BtDevice[]>([])
  const [found, setFound] = useState<BtDevice[]>([])
  const [loading, setLoading] = useState(true)
  const [op, setOp] = useState<BtOp>(null)           // current running operation
  const [opMac, setOpMac] = useState('')              // which device is busy
  const [msg, setMsg] = useState('')
  const [msgError, setMsgError] = useState(false)
  const [focusIdx, setFocusIdx] = useState(0)

  const items = [...devices, ...found]
  // Slot 0 is the Scan button, so the ring is one longer than the list. The
  // button used to carry nothing but onClick: on a television, with a pad and
  // no mouse, the one control that finds a new device could not be pressed at
  // all. Making it the first stop needs no new button to learn — you walk up
  // to it the way you walk to anything else.
  // Highest reachable index: slot 0 is the button, 1..items.length are rows.
  const SCAN_SLOT = 0
  const rowIdx = (i: number) => i - 1
  const itemsRef = useRef(items)
  useEffect(() => { itemsRef.current = items })
  // Whatever the cursor is on, so the list can be dragged to it. The Overlay
  // caps itself at 85vh with overflow-y:auto, so a box with a handful of paired
  // devices plus a scan's worth of discovered ones is taller than the panel —
  // and the highlight walked straight out of view, exactly as it did on the
  // catalogue screen before this same fix.
  const focusElRef = useRef<HTMLDivElement | HTMLButtonElement | null>(null)
  const scanRef = useRef<() => Promise<void>>(async () => {})
  const devicesRef = useRef(devices)
  const focusIdxRef = useRef(focusIdx)
  const opRef = useRef(op)
  useEffect(() => { devicesRef.current = devices }, [devices])
  useEffect(() => { focusIdxRef.current = focusIdx }, [focusIdx])
  useEffect(() => { opRef.current = op }, [op])

  const refresh = async () => {
    try {
      const known = await api.bluetooth.devices()
      setDevices(known)
      // Something that has just been paired is in both lists for a moment.
      const macs = new Set(known.map(d => d.mac))
      setFound(f => f.filter(d => !macs.has(d.mac)))
    } catch {}
  }

  useEffect(() => { refresh().finally(() => setLoading(false)) }, [])

  useSubPageGamepad(onBack, onClose)

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-up',   () => setFocusIdx(i => Math.max(0, i - 1))),
      onGp('gp:dpad-down', () => setFocusIdx(i => Math.min(itemsRef.current.length, i + 1))),
      onGp('gp:confirm', () => {
        if (opRef.current) return
        if (focusIdxRef.current === SCAN_SLOT) { void scanRef.current(); return }
        const d = itemsRef.current[focusIdxRef.current - 1]
        if (!d) return
        if (d.paired) toggleDevice(d)
        else pairDevice(d)
      }),
    ]
    return () => offs.forEach(o => o())
  }, [])

  const toggleDevice = async (d: BtDevice) => {
    if (op) return
    setOp(d.connected ? 'disconnect' : 'connect')
    setOpMac(d.mac)
    setMsg(d.connected ? `Disconnecting ${d.name}…` : `Connecting to ${d.name}…`)
    setMsgError(false)
    try {
      if (d.connected) {
        await api.bluetooth.disconnect(d.mac)
        setMsg(`${d.name} disconnected`)
      } else {
        const r = await api.bluetooth.connect(d.mac)
        if (r.ok) {
          setMsg(`${d.name} connected`)
        } else {
          setMsg(r.message || 'Connection failed')
          setMsgError(true)
        }
      }
    } catch {
      setMsg('Operation failed'); setMsgError(true)
    }
    setOp(null); setOpMac('')
    await refresh()
  }

  /**
   * Pair, then trust, then connect — all three on the backend, in that order.
   *
   * Only ever on the device the player selected. A box that paired with
   * whatever it discovered would adopt the neighbours' headphones.
   */
  const pairDevice = async (d: BtDevice) => {
    if (op) return
    setOp('pair'); setOpMac(d.mac)
    setMsg(`Pairing with ${d.name}. Keep it in pairing mode.`); setMsgError(false)
    try {
      const r = await api.bluetooth.pair(d.mac)
      setMsg(r.message || (r.ok ? 'Paired' : 'Pairing failed'))
      setMsgError(!r.ok)
    } catch {
      setMsg('Pairing failed'); setMsgError(true)
    }
    setOp(null); setOpMac('')
    await refresh()
  }

  const scan = async () => {
    if (op) return
    setOp('scan'); setMsgError(false)
    setMsg('Looking for devices. Put yours in pairing mode now.')
    try {
      const r = await api.bluetooth.scan()
      setFound(r.found ?? [])
      setMsg((r.found ?? []).length
        ? `Found ${r.found.length} device(s) not yet paired`
        : 'Nothing new in range. Hold the pairing button and scan again.')
    } catch {
      setMsg('Scan failed'); setMsgError(true)
    }
    await refresh()
    setOp(null)
  }

  useEffect(() => { scanRef.current = scan })

  // `block: 'nearest'` scrolls only when the target is actually off-screen, so
  // walking the middle of the list does not jerk the panel on every step.
  useEffect(() => {
    focusElRef.current?.scrollIntoView({ block: 'nearest' })
  }, [focusIdx, items.length])

  const removeDevice = async (e: React.MouseEvent, mac: string) => {
    e.stopPropagation()
    if (op) return
    try {
      await api.bluetooth.remove(mac)
      setMsg('Device removed'); setMsgError(false)
      await refresh()
    } catch { setMsg('Failed to remove'); setMsgError(true) }
  }

  const busy = op !== null

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="Bluetooth" onBack={onBack} />

      {/* Scan button */}
      <button
        ref={el => { if (focusIdx === SCAN_SLOT) focusElRef.current = el }}
        onClick={() => { setFocusIdx(SCAN_SLOT); void scan() }}
        disabled={busy}
        style={{
          width: '100%', marginBottom: 14, padding: '10px 16px', borderRadius: 10,
          background: op === 'scan' ? 'color-mix(in srgb, var(--gc-accent, #b8501b) 30%, transparent)'
            : focusIdx === SCAN_SLOT ? 'color-mix(in srgb, var(--gc-accent, #b8501b) 24%, transparent)'
            : 'color-mix(in srgb, var(--gc-accent, #b8501b) 15%, transparent)',
          border: `1px solid color-mix(in srgb, var(--gc-accent, #b8501b) ${focusIdx === SCAN_SLOT ? 75 : 40}%, transparent)`,
          color: 'var(--gc-accent-bright, #f8cfa9)',
          cursor: busy ? 'default' : 'pointer', fontSize: 15, fontWeight: 600,
          opacity: busy && op !== 'scan' ? 0.5 : 1,
        }}
      >
        {op === 'scan' ? 'Scanning…' : 'Scan for devices'}
      </button>

      {/* Status message */}
      {msg && (
        <div style={{ fontSize: 15, marginBottom: 12, padding: '8px 12px', borderRadius: 8,
          background: msgError ? 'rgba(239,68,68,0.08)' : 'rgba(255,255,255,0.04)',
          color: msgError ? '#f87171' : 'var(--gc-accent-soft, #f2a46a)', fontWeight: msgError ? 600 : 400 }}>
          {msg}
        </div>
      )}

      {/* Device list — paired first, then whatever the scan turned up. */}
      {loading ? (
        <div style={{ color: 'var(--gc-ink-3)', fontSize: 15, textAlign: 'center', padding: 16 }}>Loading…</div>
      ) : items.length === 0 ? (
        <div style={{ color: 'var(--gc-ink-3)', fontSize: 15, textAlign: 'center', padding: 16 }}>
          No paired devices yet — put yours in pairing mode, then press ✕ on Scan above
        </div>
      ) : items.map((d, di) => {
        const isFocused = di === rowIdx(focusIdx)
        const isThisBusy = opMac === d.mac && busy
        // A heading before the first of each list, so "already yours" and "in
        // the room right now" are never mistaken for one another.
        const head = di === 0 || items[di - 1].paired !== d.paired
        const label = d.paired ? 'Paired' : 'Found, not paired yet'

        return (
          <div key={d.mac}>
            {head && (
              <div style={{
                fontSize: 15, fontWeight: 600,
                color: 'var(--gc-ink-3)', margin: '10px 2px 6px',
              }}>
                {label}
              </div>
            )}

            <div
              ref={el => { if (isFocused) focusElRef.current = el }}
              onClick={() => { setFocusIdx(di + 1); d.paired ? toggleDevice(d) : pairDevice(d) }}
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '13px 16px', borderRadius: 12, marginBottom: 8,
                cursor: busy ? 'default' : 'pointer',
                background: isFocused ? 'color-mix(in srgb, var(--gc-accent, #b8501b) 18%, transparent)' : d.connected ? 'color-mix(in srgb, var(--gc-accent, #b8501b) 8%, transparent)' : 'rgba(255,255,255,0.04)',
                border: isFocused ? '1px solid color-mix(in srgb, var(--gc-accent, #b8501b) 60%, transparent)' : d.connected ? '1px solid color-mix(in srgb, var(--gc-accent, #b8501b) 25%, transparent)' : '1px solid rgba(255,255,255,0.07)',
                opacity: busy && !isThisBusy ? 0.5 : 1,
                transition: 'all 0.15s',
              }}
            >
              {/* Filled = connected, ring = paired, faint = only seen. Shape as well as colour. */}
              <div style={{ width: 28, display: 'flex', justifyContent: 'center' }}>
                <span style={{
                  width: 10, height: 10, borderRadius: '50%',
                  background: d.connected ? 'var(--gc-accent, #b8501b)' : 'transparent',
                  border: `2px solid ${d.connected ? 'var(--gc-accent, #b8501b)' : d.paired ? 'rgba(255,255,255,0.7)' : 'rgba(255,255,255,0.25)'}`,
                }} />
              </div>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {d.name}
                </div>
                <div style={{ fontSize: 14, color: 'var(--gc-ink-3)', marginTop: 2 }}>
                  {isThisBusy
                    ? (!d.paired ? 'Pairing…' : d.connected ? 'Disconnecting…' : 'Connecting…')
                    : (d.connected ? 'Connected' : d.mac)}
                </div>
              </div>

              <div style={{
                fontSize: 14, fontWeight: 600, padding: '4px 10px', borderRadius: 6,
                background: d.connected ? 'rgba(248,113,113,0.12)' : 'color-mix(in srgb, var(--gc-accent, #b8501b) 20%, transparent)',
                border: `1px solid ${d.connected ? 'rgba(248,113,113,0.3)' : 'color-mix(in srgb, var(--gc-accent, #b8501b) 35%, transparent)'}`,
                color: d.connected ? '#f87171' : 'var(--gc-accent-bright, #f8cfa9)',
              }}>
                {isThisBusy ? '…' : !d.paired ? 'Pair' : d.connected ? 'Disconnect' : 'Connect'}
              </div>

              {/* Forgetting a device only makes sense for one the box knows. */}
              {d.paired && !d.connected && (
                <div
                  onClick={e => removeDevice(e, d.mac)}
                  title="Remove device"
                  style={{ fontSize: 16, color: 'var(--gc-ink-3)', cursor: 'pointer', padding: '0 4px', lineHeight: 1 }}
                >
                  ×
                </div>
              )}
            </div>
          </div>
        )
      })}

      <div style={{ marginTop: 8, textAlign: 'center', fontSize: 14, color: 'var(--gc-ink-3)', }}>
        <PadHints text={`↑↓ Navigate · ✕ ${
          focusIdx === SCAN_SLOT ? 'Scan'
            : items[rowIdx(focusIdx)] && !items[rowIdx(focusIdx)].paired ? 'Pair'
            : 'Connect/Disconnect'}`} />
      </div>
    </Overlay>
  )
}
