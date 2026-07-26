import { useState, useEffect, useRef } from 'react'
import { Overlay, BackHeader } from '../../ui'
import { api } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { useSubPageGamepad } from './useSubPageGamepad'

type BtDevice = { mac: string; name: string; connected: boolean }
type BtOp = 'connect' | 'disconnect' | 'scan' | null

export function BluetoothPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [devices, setDevices] = useState<BtDevice[]>([])
  const [loading, setLoading] = useState(true)
  const [op, setOp] = useState<BtOp>(null)           // current running operation
  const [opMac, setOpMac] = useState('')              // which device is busy
  const [msg, setMsg] = useState('')
  const [msgError, setMsgError] = useState(false)
  const [focusIdx, setFocusIdx] = useState(0)

  const devicesRef = useRef(devices)
  const focusIdxRef = useRef(focusIdx)
  const opRef = useRef(op)
  useEffect(() => { devicesRef.current = devices }, [devices])
  useEffect(() => { focusIdxRef.current = focusIdx }, [focusIdx])
  useEffect(() => { opRef.current = op }, [op])

  const refresh = async () => {
    try { setDevices(await api.bluetooth.devices()) } catch {}
  }

  useEffect(() => { refresh().finally(() => setLoading(false)) }, [])

  useSubPageGamepad(onBack, onClose)

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-up',   () => setFocusIdx(i => Math.max(0, i - 1))),
      onGp('gp:dpad-down', () => setFocusIdx(i => Math.min(devicesRef.current.length - 1, i + 1))),
      onGp('gp:confirm', () => {
        if (opRef.current) return
        const d = devicesRef.current[focusIdxRef.current]
        if (d) toggleDevice(d)
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

  const scan = async () => {
    if (op) return
    setOp('scan'); setMsg('Scanning for devices (8s)…'); setMsgError(false)
    try { await api.bluetooth.scan() } catch {}
    await refresh()
    setOp(null); setMsg('Scan complete')
  }

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
      <BackHeader label="BLUETOOTH" onBack={onBack} />

      {/* Scan button */}
      <button
        onClick={scan}
        disabled={busy}
        style={{
          width: '100%', marginBottom: 14, padding: '10px 16px', borderRadius: 10,
          background: op === 'scan' ? 'color-mix(in srgb, var(--gc-accent, #7c3aed) 30%, transparent)' : 'color-mix(in srgb, var(--gc-accent, #7c3aed) 15%, transparent)',
          border: '1px solid color-mix(in srgb, var(--gc-accent, #7c3aed) 40%, transparent)', color: 'var(--gc-accent-bright, #c4b5fd)',
          cursor: busy ? 'default' : 'pointer', fontSize: 13, fontWeight: 600,
          opacity: busy && op !== 'scan' ? 0.5 : 1,
        }}
      >
        {op === 'scan' ? '⏳ Scanning…' : '🔍 Scan for devices'}
      </button>

      {/* Status message */}
      {msg && (
        <div style={{ fontSize: 13, marginBottom: 12, padding: '8px 12px', borderRadius: 8,
          background: msgError ? 'rgba(239,68,68,0.08)' : 'rgba(255,255,255,0.04)',
          color: msgError ? '#f87171' : 'var(--gc-accent-soft, #a78bfa)', fontWeight: msgError ? 600 : 400 }}>
          {msg}
        </div>
      )}

      {/* Device list */}
      {loading ? (
        <div style={{ color: 'rgba(255,255,255,0.3)', fontSize: 13, textAlign: 'center', padding: 16 }}>Loading…</div>
      ) : devices.length === 0 ? (
        <div style={{ color: 'rgba(255,255,255,0.3)', fontSize: 13, textAlign: 'center', padding: 16 }}>
          No paired devices — scan to find new ones
        </div>
      ) : devices.map((d, di) => {
        const isFocused = di === focusIdx
        const isThisBusy = opMac === d.mac && busy
        return (
          <div
            key={d.mac}
            onClick={() => { setFocusIdx(di); toggleDevice(d) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 12,
              padding: '13px 16px', borderRadius: 12, marginBottom: 8,
              cursor: busy ? 'default' : 'pointer',
              background: isFocused ? 'color-mix(in srgb, var(--gc-accent, #7c3aed) 18%, transparent)' : d.connected ? 'color-mix(in srgb, var(--gc-accent, #7c3aed) 8%, transparent)' : 'rgba(255,255,255,0.04)',
              border: isFocused ? '1px solid color-mix(in srgb, var(--gc-accent, #7c3aed) 60%, transparent)' : d.connected ? '1px solid color-mix(in srgb, var(--gc-accent, #7c3aed) 25%, transparent)' : '1px solid rgba(255,255,255,0.07)',
              opacity: busy && !isThisBusy ? 0.5 : 1,
              transition: 'all 0.15s',
            }}
          >
            {/* Icon */}
            <div style={{ fontSize: 20, width: 28, textAlign: 'center' }}>
              {d.connected ? '🔵' : '⚪'}
            </div>

            {/* Info */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {d.name}
              </div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', marginTop: 2 }}>
                {isThisBusy ? (d.connected ? 'Disconnecting…' : 'Connecting…') : (d.connected ? 'Connected' : d.mac)}
              </div>
            </div>

            {/* Action badge */}
            <div style={{
              fontSize: 11, fontWeight: 600, padding: '4px 10px', borderRadius: 6,
              background: d.connected ? 'rgba(248,113,113,0.12)' : 'color-mix(in srgb, var(--gc-accent, #7c3aed) 20%, transparent)',
              border: `1px solid ${d.connected ? 'rgba(248,113,113,0.3)' : 'color-mix(in srgb, var(--gc-accent, #7c3aed) 35%, transparent)'}`,
              color: d.connected ? '#f87171' : 'var(--gc-accent-bright, #c4b5fd)',
            }}>
              {isThisBusy ? '…' : (d.connected ? 'Disconnect' : 'Connect')}
            </div>

            {/* Remove button */}
            {!d.connected && (
              <div
                onClick={e => removeDevice(e, d.mac)}
                title="Remove device"
                style={{ fontSize: 16, color: 'rgba(255,255,255,0.2)', cursor: 'pointer', padding: '0 4px', lineHeight: 1 }}
              >
                ×
              </div>
            )}
          </div>
        )
      })}

      <div style={{ marginTop: 8, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        ↑↓ Navigate · ✕ Connect/Disconnect
      </div>
    </Overlay>
  )
}
