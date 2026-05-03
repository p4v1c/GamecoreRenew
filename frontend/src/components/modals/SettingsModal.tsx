import { useState, useEffect, useRef, useCallback } from 'react'
import { Overlay, OverlayLabel, BackHeader, Toggle, SliderRow, Bars } from '../ui'
import { VirtualKeyboard } from '../ui/VirtualKeyboard'
import { api } from '../../api'
import { useStore } from '../../store'
import { onGp } from '../../hooks/useGamepad'
import { onWsEvent } from '../../hooks/useWebSocket'

interface Props { onClose: () => void }

type Page = 'main' | 'wifi' | 'audio' | 'bluetooth' | 'update' | 'desktop'

const ITEMS = [
  { id: 'wifi',      icon: '📶', label: 'Wi-Fi',       sub: 'Manage networks' },
  { id: 'audio',     icon: '🔊', label: 'Audio',        sub: 'Volume & output' },
  { id: 'bluetooth', icon: '◉',  label: 'Bluetooth',    sub: 'Devices & pairing' },
  { id: 'update',    icon: '↑',  label: 'Update',       sub: 'Check for updates' },
  { id: 'desktop',   icon: '⎋',  label: 'Desktop Mode', sub: 'Return to system', danger: true },
] as const

export default function SettingsModal({ onClose }: Props) {
  const [page, setPage] = useState<Page>('main')
  const [focusIdx, setFocusIdx] = useState(0)
  const { openModal, closeModal } = useStore()

  // Register / unregister in the modal stack
  useEffect(() => {
    openModal()
    return () => closeModal()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const back = useCallback(() => setPage('main'), [])

  // Stable ref for focusIdx to avoid stale closures
  const focusIdxRef = useRef(focusIdx)
  useEffect(() => { focusIdxRef.current = focusIdx }, [focusIdx])

  // Gamepad — only active on the main page
  useEffect(() => {
    if (page !== 'main') return
    const offs = [
      onGp('gp:dpad-up',   () => setFocusIdx(i => Math.max(0, i - 1))),
      onGp('gp:dpad-down', () => setFocusIdx(i => Math.min(ITEMS.length - 1, i + 1))),
      onGp('gp:confirm',   () => setPage(ITEMS[focusIdxRef.current].id as Page)),
      onGp('gp:back',      onClose),
      onGp('gp:menu',      onClose),
    ]
    return () => offs.forEach(o => o())
  }, [page, onClose])

  if (page === 'wifi')      return <WifiPage      onClose={onClose} onBack={back} />
  if (page === 'audio')     return <AudioPage     onClose={onClose} onBack={back} />
  if (page === 'bluetooth') return <BluetoothPage onClose={onClose} onBack={back} />
  if (page === 'update')    return <UpdatePage    onClose={onClose} onBack={back} />
  if (page === 'desktop')   return <DesktopPage   onClose={onClose} onBack={back} />

  return (
    <Overlay onClose={onClose}>
      <OverlayLabel text="SETTINGS" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {ITEMS.map((it, idx) => (
          <div key={it.id} onClick={() => setPage(it.id as Page)} style={{
            display: 'flex', alignItems: 'center', gap: 18, padding: '18px 22px',
            borderRadius: 14, cursor: 'pointer',
            background: idx === focusIdx ? 'rgba(124,58,237,0.15)' : 'rgba(255,255,255,0.04)',
            border: idx === focusIdx ? '1px solid rgba(124,58,237,0.4)' : '1px solid rgba(255,255,255,0.07)',
            transition: 'all 0.15s',
          }}>
            <div style={{ fontSize: 26, width: 36, textAlign: 'center' }}>{it.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 17, fontWeight: 600, color: (it as typeof it & { danger?: boolean }).danger ? '#fca5a5' : '#fff' }}>{it.label}</div>
              <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.38)', marginTop: 4 }}>{it.sub}</div>
            </div>
            <div style={{ color: 'rgba(255,255,255,0.25)', fontSize: 22 }}>›</div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 12, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        ↑↓ Navigate · ✕ Select · ○ Close
      </div>
    </Overlay>
  )
}

// ── Shared gamepad hook for sub-pages ─────────────────────────────────────────

function useSubPageGamepad(onBack: () => void, onClose: () => void, enabled = true) {
  const onBackRef  = useRef(onBack)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onBackRef.current  = onBack  }, [onBack])
  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  useEffect(() => {
    if (!enabled) return
    const offs = [
      onGp('gp:back', () => onBackRef.current()),
      onGp('gp:menu', () => onCloseRef.current()),
    ]
    return () => offs.forEach(o => o())
  }, [enabled])
}

// ── Sub-pages ─────────────────────────────────────────────────────────────────

type WifiNetwork = { ssid: string; signal: number; secured: boolean; connected: boolean }
type WifiStatus  = { connected: boolean; ssid: string; ip: string; iface: string }

function WifiPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [networks, setNetworks]     = useState<WifiNetwork[]>([])
  const [wifiStatus, setWifiStatus] = useState<WifiStatus | null>(null)
  const [loading, setLoading]       = useState(true)
  const [busy, setBusy]             = useState(false)
  const [msg, setMsg]               = useState('')
  const [msgError, setMsgError]     = useState(false)
  const [showKeyboard, setShowKeyboard] = useState(false)
  const [pendingSsid, setPendingSsid]   = useState('')
  const [focusIdx, setFocusIdx]     = useState(0)

  const networksRef = useRef(networks)
  const focusIdxRef = useRef(focusIdx)
  const busyRef     = useRef(busy)
  useEffect(() => { networksRef.current = networks }, [networks])
  useEffect(() => { focusIdxRef.current = focusIdx }, [focusIdx])
  useEffect(() => { busyRef.current = busy }, [busy])

  const refresh = async () => {
    try {
      const [nets, st] = await Promise.all([api.wifi.networks(), api.wifi.status()])
      setNetworks(nets)
      setWifiStatus(st)
    } catch {}
    setLoading(false)
  }

  useEffect(() => { refresh() }, [])

  useSubPageGamepad(
    showKeyboard ? () => setShowKeyboard(false) : onBack,
    onClose,
    !showKeyboard,
  )

  const handleNetworkRef = useRef<(n: WifiNetwork) => void>(() => {})

  useEffect(() => {
    if (showKeyboard) return
    const offs = [
      onGp('gp:dpad-up',   () => setFocusIdx(i => Math.max(0, i - 1))),
      onGp('gp:dpad-down', () => setFocusIdx(i => Math.min(networksRef.current.length - 1, i + 1))),
      onGp('gp:confirm',   () => { if (!busyRef.current) { const n = networksRef.current[focusIdxRef.current]; if (n) handleNetworkRef.current(n) } }),
    ]
    return () => offs.forEach(o => o())
  }, [showKeyboard])

  const doDisconnect = async () => {
    setBusy(true); setMsg('Disconnecting…'); setMsgError(false)
    try {
      const r = await api.wifi.disconnect()
      setMsg(r.ok ? 'Disconnected' : (r.error ?? 'Disconnect failed'))
      setMsgError(!r.ok)
    } catch { setMsg('Disconnect failed'); setMsgError(true) }
    setBusy(false)
    await refresh()
  }

  const doConnect = async (ssid: string, pwd: string) => {
    setShowKeyboard(false)
    setBusy(true); setMsg(`Connecting to ${ssid}…`); setMsgError(false)
    try {
      const r = await api.wifi.connect(ssid, pwd)
      if (r.ok) {
        setMsg(`Connected to ${ssid}`); setMsgError(false)
        await refresh()
      } else {
        setMsg(r.wrong_password ? 'Wrong password — try again' : (r.error ?? 'Connection failed'))
        setMsgError(true)
      }
    } catch { setMsg('Connection failed'); setMsgError(true) }
    setBusy(false)
  }

  const handleNetwork = (n: WifiNetwork) => {
    if (n.connected) { doDisconnect(); return }
    if (n.secured) { setPendingSsid(n.ssid); setShowKeyboard(true) }
    else doConnect(n.ssid, '')
  }
  handleNetworkRef.current = handleNetwork

  if (showKeyboard) {
    return (
      <Overlay onClose={onClose}>
        <BackHeader label="WI-FI" onBack={() => setShowKeyboard(false)} />
        <VirtualKeyboard
          title={`Password for "${pendingSsid}"`}
          password
          onConfirm={pwd => doConnect(pendingSsid, pwd)}
          onCancel={() => setShowKeyboard(false)}
        />
      </Overlay>
    )
  }

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="WI-FI" onBack={onBack} />

      {/* Current connection banner */}
      {wifiStatus?.connected && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '10px 14px', borderRadius: 10, marginBottom: 14,
          background: 'rgba(74,222,128,0.08)', border: '1px solid rgba(74,222,128,0.25)',
        }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#4ade80' }}>✓ {wifiStatus.ssid}</div>
            {wifiStatus.ip && <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginTop: 2 }}>{wifiStatus.ip} · {wifiStatus.iface}</div>}
          </div>
          <button
            onClick={doDisconnect}
            disabled={busy}
            style={{ padding: '5px 12px', borderRadius: 7, border: '1px solid rgba(248,113,113,0.4)', background: 'rgba(248,113,113,0.1)', color: '#f87171', fontSize: 12, cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.5 : 1 }}
          >
            Disconnect
          </button>
        </div>
      )}

      {/* Status/error message */}
      {msg && (
        <div style={{
          fontSize: 13, marginBottom: 12, padding: '8px 12px', borderRadius: 8,
          background: msgError ? 'rgba(239,68,68,0.08)' : 'rgba(255,255,255,0.04)',
          color: msgError ? '#f87171' : '#a78bfa', fontWeight: msgError ? 600 : 400,
        }}>
          {busy ? '⏳ ' : ''}{msg}
        </div>
      )}

      {/* Refresh button */}
      <button
        onClick={() => { setLoading(true); refresh() }}
        disabled={busy || loading}
        style={{ marginBottom: 12, padding: '7px 14px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.5)', fontSize: 12, cursor: 'pointer', opacity: busy || loading ? 0.4 : 1 }}
      >
        {loading ? 'Scanning…' : '↺ Refresh'}
      </button>

      {/* Network list */}
      {!loading && networks.length === 0 && (
        <div style={{ color: 'rgba(255,255,255,0.3)', fontSize: 13, textAlign: 'center', padding: 16 }}>No networks found</div>
      )}
      {networks.map((n, ni) => (
        <div
          key={n.ssid}
          onClick={() => { setFocusIdx(ni); if (!busy) handleNetwork(n) }}
          style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: '11px 14px',
            borderRadius: 10, marginBottom: 6, cursor: busy ? 'default' : 'pointer',
            background: ni === focusIdx ? 'rgba(124,58,237,0.2)' : n.connected ? 'rgba(74,222,128,0.06)' : 'rgba(255,255,255,0.04)',
            border: ni === focusIdx ? '1px solid rgba(124,58,237,0.6)' : n.connected ? '1px solid rgba(74,222,128,0.25)' : '1px solid rgba(255,255,255,0.06)',
            opacity: busy && !n.connected ? 0.6 : 1,
            transition: 'all 0.12s',
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: n.connected ? 700 : 500, color: n.connected ? '#4ade80' : '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {n.connected ? '✓ ' : ''}{n.ssid}
            </div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', marginTop: 2 }}>
              {n.secured ? '🔒 Secured' : '🔓 Open'}
            </div>
          </div>
          <Bars signal={n.signal} />
        </div>
      ))}

      <div style={{ marginTop: 8, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        ↑↓ Navigate · ✕ Connect/Disconnect
      </div>
    </Overlay>
  )
}

function AudioPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [volume, setVolumeState] = useState(50)
  const [sinks, setSinks] = useState<{ id: string; name: string; default: boolean }[]>([])
  const [sinkFocus, setSinkFocus] = useState(0)
  const [error, setError] = useState('')

  const volumeRef = useRef(volume)
  const sinksRef  = useRef(sinks)
  const sinkFocusRef = useRef(sinkFocus)
  useEffect(() => { volumeRef.current = volume }, [volume])
  useEffect(() => { sinksRef.current = sinks }, [sinks])
  useEffect(() => { sinkFocusRef.current = sinkFocus }, [sinkFocus])

  useEffect(() => {
    api.audio.get().then(r => setVolumeState(r.volume)).catch(() => {})
    api.audio.sinks().then(list => {
      setSinks(list)
      const defIdx = list.findIndex(s => s.default)
      setSinkFocus(defIdx >= 0 ? defIdx : 0)
    }).catch(() => {})
  }, [])

  useSubPageGamepad(onBack, onClose)

  const applyVolume = (v: number) => {
    setVolumeState(v)
    api.audio.setVolume(v)
      .then((r: unknown) => { const res = r as { ok: boolean; error?: string }; setError(res.ok ? '' : (res.error ?? 'Failed')) })
      .catch(() => setError('Backend unreachable'))
  }

  const applySink = (id: string) => {
    api.audio.setSink(id)
      .then(() => {
        setSinks(prev => prev.map(s => ({ ...s, default: s.id === id })))
        setError('')
      })
      .catch(() => setError('Failed to change output'))
  }

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-right', () => applyVolume(Math.min(100, volumeRef.current + 5))),
      onGp('gp:dpad-left',  () => applyVolume(Math.max(0,   volumeRef.current - 5))),
      onGp('gp:dpad-up',    () => setSinkFocus(i => Math.max(0, i - 1))),
      onGp('gp:dpad-down',  () => setSinkFocus(i => Math.min(sinksRef.current.length - 1, i + 1))),
      onGp('gp:confirm',    () => { const s = sinksRef.current[sinkFocusRef.current]; if (s) applySink(s.id) }),
    ]
    return () => offs.forEach(o => o())
  }, [])

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="AUDIO" onBack={onBack} />
      <SliderRow label="Volume" value={volume} onChange={applyVolume} />
      {error && (
        <div style={{ fontSize: 12, color: '#f87171', margin: '8px 0', padding: '8px 12px', borderRadius: 8, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
          ⚠ {error}
        </div>
      )}
      {sinks.length > 0 && (
        <>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', letterSpacing: 2, margin: '16px 0 8px' }}>OUTPUT</div>
          {sinks.map((s, i) => (
            <div key={s.id} onClick={() => { setSinkFocus(i); applySink(s.id) }} style={{
              padding: '12px 16px', borderRadius: 10, marginBottom: 6, cursor: 'pointer',
              background: i === sinkFocus ? 'rgba(124,58,237,0.2)' : s.default ? 'rgba(124,58,237,0.08)' : 'rgba(255,255,255,0.04)',
              border: i === sinkFocus ? '1px solid rgba(124,58,237,0.6)' : s.default ? '1px solid rgba(124,58,237,0.3)' : '1px solid rgba(255,255,255,0.07)',
              fontSize: 14, color: '#fff',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              transition: 'all 0.12s',
            }}>
              <span>{s.name}</span>
              {s.default && <span style={{ fontSize: 11, color: '#a78bfa', fontWeight: 600 }}>Active</span>}
            </div>
          ))}
        </>
      )}
      <div style={{ marginTop: 12, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        ←→ Volume · ↑↓ Select output · ✕ Apply
      </div>
    </Overlay>
  )
}

type BtDevice = { mac: string; name: string; connected: boolean }
type BtOp = 'connect' | 'disconnect' | 'scan' | null

function BluetoothPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
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
          background: op === 'scan' ? 'rgba(124,58,237,0.3)' : 'rgba(124,58,237,0.15)',
          border: '1px solid rgba(124,58,237,0.4)', color: '#c4b5fd',
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
          color: msgError ? '#f87171' : '#a78bfa', fontWeight: msgError ? 600 : 400 }}>
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
              background: isFocused ? 'rgba(124,58,237,0.18)' : d.connected ? 'rgba(124,58,237,0.08)' : 'rgba(255,255,255,0.04)',
              border: isFocused ? '1px solid rgba(124,58,237,0.6)' : d.connected ? '1px solid rgba(124,58,237,0.25)' : '1px solid rgba(255,255,255,0.07)',
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
              background: d.connected ? 'rgba(248,113,113,0.12)' : 'rgba(124,58,237,0.2)',
              border: `1px solid ${d.connected ? 'rgba(248,113,113,0.3)' : 'rgba(124,58,237,0.35)'}`,
              color: d.connected ? '#f87171' : '#c4b5fd',
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

function UpdatePage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [info, setInfo] = useState<{ update_available: boolean; current: string; latest: string } | null>(null)
  const [checkError, setCheckError] = useState('')
  const [checking, setChecking] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [log, setLog] = useState<string[]>([])
  const [focusIdx, setFocusIdx] = useState(0)
  const logEndRef = useRef<HTMLDivElement>(null)

  const focusIdxRef  = useRef(focusIdx)
  const checkingRef  = useRef(checking)
  const installingRef = useRef(installing)
  const infoRef      = useRef(info)
  useEffect(() => { focusIdxRef.current  = focusIdx  }, [focusIdx])
  useEffect(() => { checkingRef.current  = checking  }, [checking])
  useEffect(() => { installingRef.current = installing }, [installing])
  useEffect(() => { infoRef.current      = info      }, [info])

  useSubPageGamepad(onBack, onClose)

  useEffect(() => {
    const btnCount = () => infoRef.current?.update_available ? 2 : 1
    const offs = [
      onGp('gp:left',  () => setFocusIdx(i => Math.max(0, i - 1))),
      onGp('gp:right', () => setFocusIdx(i => Math.min(btnCount() - 1, i + 1))),
      onGp('gp:confirm', () => {
        if (checkingRef.current || installingRef.current) return
        if (focusIdxRef.current === 0) checkRef.current()
        else if (focusIdxRef.current === 1) applyRef.current()
      }),
    ]
    return () => offs.forEach(o => o())
  }, [])

  const checkRef = useRef<() => void>(() => {})
  const applyRef = useRef<() => void>(() => {})

  const check = useCallback(async () => {
    setChecking(true); setCheckError('')
    try {
      setInfo(await api.update.check())
    } catch (e: unknown) {
      setInfo(null)
      const msg = e instanceof Error ? e.message : String(e)
      setCheckError(msg.includes('503') ? 'Cannot reach GitHub — check your internet connection' : `Check failed: ${msg}`)
    }
    setChecking(false)
  }, [])

  // Auto-check on open
  useEffect(() => { check() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Subscribe to update log stream
  useEffect(() => {
    const off1 = onWsEvent('update:log', d => {
      setLog(prev => [...prev, d.line as string])
      setTimeout(() => logEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 30)
    })
    const off2 = onWsEvent('update:done', () => setInstalling(false))
    return () => { off1(); off2() }
  }, [])

  const apply = async () => {
    setLog([])
    setInstalling(true)
    try { await api.update.apply() } catch { setInstalling(false) }
  }

  checkRef.current = check
  applyRef.current = apply

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="UPDATE" onBack={onBack} />

      {/* Error banner */}
      {checkError && !checking && (
        <div style={{ padding: '12px 16px', borderRadius: 10, marginBottom: 14, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#f87171', fontSize: 13 }}>
          ⚠ {checkError}
        </div>
      )}

      {/* Version banner */}
      {info && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '14px 18px', borderRadius: 12, marginBottom: 14,
          background: info.update_available ? 'rgba(74,222,128,0.08)' : 'rgba(255,255,255,0.04)',
          border: info.update_available ? '1px solid rgba(74,222,128,0.3)' : '1px solid rgba(255,255,255,0.08)',
        }}>
          <div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', letterSpacing: 2, marginBottom: 4 }}>INSTALLED</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#fff' }}>{info.current}</div>
          </div>
          {info.update_available ? (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 11, color: 'rgba(74,222,128,0.7)', letterSpacing: 2, marginBottom: 4 }}>AVAILABLE</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: '#4ade80' }}>{info.latest}</div>
            </div>
          ) : (
            <div style={{ fontSize: 13, color: '#4ade80', fontWeight: 600 }}>✓ Up to date</div>
          )}
        </div>
      )}

      <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
        <button onClick={check} disabled={checking || installing} style={{
          flex: 1, padding: '10px', borderRadius: 10, cursor: 'pointer', fontSize: 13, fontWeight: 600,
          background: 'rgba(124,58,237,0.15)', color: '#c4b5fd',
          border: focusIdx === 0 ? '2px solid rgba(124,58,237,0.9)' : '1px solid rgba(124,58,237,0.35)',
          outline: 'none', opacity: checking || installing ? 0.5 : 1,
        }}>
          {checking ? '⏳ Checking…' : '🔍 Check again'}
        </button>
        {info?.update_available && (
          <button onClick={apply} disabled={installing} style={{
            flex: 1, padding: '10px', borderRadius: 10, cursor: 'pointer', fontSize: 13, fontWeight: 700,
            background: installing ? 'rgba(74,222,128,0.08)' : 'rgba(74,222,128,0.15)',
            border: focusIdx === 1 ? '2px solid rgba(74,222,128,0.9)' : '1px solid rgba(74,222,128,0.4)',
            outline: 'none', color: '#4ade80',
            opacity: installing ? 0.6 : 1,
          }}>
            {installing ? '⏳ Installing…' : '↑ Install update'}
          </button>
        )}
      </div>

      {log.length > 0 && (
        <div style={{ fontFamily: 'monospace', fontSize: 12, color: 'rgba(255,255,255,0.55)', background: 'rgba(0,0,0,0.35)', borderRadius: 8, padding: 12, maxHeight: 200, overflowY: 'auto' }}>
          {log.map((l, i) => <div key={i} style={{ marginBottom: 2 }}>{l}</div>)}
          <div ref={logEndRef} />
        </div>
      )}
    </Overlay>
  )
}

function DesktopPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const exitRef = useRef<() => void>(() => {})

  const doExit = () => { window.gamecore?.quit(); window.close() }
  exitRef.current = doExit

  useSubPageGamepad(onBack, onClose)

  useEffect(() => {
    const off = onGp('gp:confirm', () => exitRef.current())
    return off
  }, [])

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="DESKTOP MODE" onBack={onBack} />
      <div style={{ padding: '20px 22px', borderRadius: 14, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', marginBottom: 24, color: '#fca5a5', fontSize: 15, lineHeight: 1.8 }}>
        Exit GameCore and return to the system desktop environment.
      </div>
      <div onClick={doExit} style={{ padding: 16, borderRadius: 14, cursor: 'pointer', background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)', color: '#fca5a5', fontWeight: 700, textAlign: 'center', fontSize: 16 }}>
        ✕ Exit to Desktop
      </div>
      <div style={{ marginTop: 8, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        ✕ Confirm · ○ Cancel
      </div>
    </Overlay>
  )
}
