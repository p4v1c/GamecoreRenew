import { useState, useEffect, useRef } from 'react'
import { Overlay, BackHeader, Bars } from '../../ui'
import { VirtualKeyboard } from '../../ui/VirtualKeyboard'
import { api } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { useSubPageGamepad } from './useSubPageGamepad'

type WifiNetwork = { ssid: string; signal: number; secured: boolean; connected: boolean }
type WifiStatus  = { connected: boolean; ssid: string; ip: string; iface: string; ethernet: { connected: boolean; iface: string; ip: string } }

export function WifiPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [networks, setNetworks]     = useState<WifiNetwork[]>([])
  const [wifiStatus, setWifiStatus] = useState<WifiStatus | null>(null)
  const [loading, setLoading]       = useState(true)
  const [busy, setBusy]             = useState(false)
  const [msg, setMsg]               = useState('')
  const [msgError, setMsgError]     = useState(false)
  const [showKeyboard, setShowKeyboard] = useState(false)
  const [pendingSsid, setPendingSsid]   = useState('')
  const [focusIdx, setFocusIdx]     = useState(0)
  const [showWifiAnyway, setShowWifiAnyway] = useState(false)

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

  const onEthernet = !!wifiStatus?.ethernet?.connected

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="WI-FI" onBack={onBack} />

      {/* Wired connection — no need for Wi-Fi */}
      {onEthernet && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '14px 16px', borderRadius: 12, marginBottom: 14,
          background: 'rgba(74,222,128,0.08)', border: '1px solid rgba(74,222,128,0.25)',
        }}>
          <span style={{ fontSize: 22 }}>🔌</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#4ade80' }}>Connected via Ethernet</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginTop: 2 }}>
              Wired network active{wifiStatus?.ethernet.ip ? ` · ${wifiStatus.ethernet.ip}` : ''}
              {wifiStatus?.ethernet.iface ? ` · ${wifiStatus.ethernet.iface}` : ''} — Wi-Fi not needed
            </div>
          </div>
        </div>
      )}

      {/* Current connection banner */}
      {!onEthernet && wifiStatus?.connected && (
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
          color: msgError ? '#f87171' : 'var(--gc-accent-soft, #a78bfa)', fontWeight: msgError ? 600 : 400,
        }}>
          {busy ? '⏳ ' : ''}{msg}
        </div>
      )}

      {/* On ethernet: hide the Wi-Fi list (not needed) unless asked */}
      {onEthernet && !showWifiAnyway && (
        <div
          onClick={() => setShowWifiAnyway(true)}
          style={{ textAlign: 'center', fontSize: 12, color: 'rgba(255,255,255,0.35)', cursor: 'pointer', padding: 8 }}
        >
          Show Wi-Fi networks anyway ›
        </div>
      )}

      {(!onEthernet || showWifiAnyway) && <>
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
            background: ni === focusIdx ? 'color-mix(in srgb, var(--gc-accent, #7c3aed) 20%, transparent)' : n.connected ? 'rgba(74,222,128,0.06)' : 'rgba(255,255,255,0.04)',
            border: ni === focusIdx ? '1px solid color-mix(in srgb, var(--gc-accent, #7c3aed) 60%, transparent)' : n.connected ? '1px solid rgba(74,222,128,0.25)' : '1px solid rgba(255,255,255,0.06)',
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
      </>}
    </Overlay>
  )
}
