import { useState, useEffect, useRef, type ReactNode } from 'react'
import { Overlay, BackHeader, Bars, Glyph } from '../../ui'
import { VirtualKeyboard } from '../../ui/VirtualKeyboard'
import { api } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { useSubPageGamepad } from './useSubPageGamepad'
import { PadHints } from '../../../lib/padKey'

type WifiNetwork = { ssid: string; signal: number; secured: boolean; connected: boolean }
type WifiStatus  = { connected: boolean; ssid: string; ip: string; iface: string; radio?: boolean | null; ethernet: { connected: boolean; iface: string; ip: string } }

const REFRESH_MS = 10000
/** `focusIdx` of the radio row, above network 0. */
const RADIO = -1

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
  // Turning the radio off with no cable takes the box offline: two presses.
  const [armed, setArmed] = useState(false)

  const networksRef = useRef(networks)
  const focusIdxRef = useRef(focusIdx)
  const busyRef     = useRef(busy)
  useEffect(() => { networksRef.current = networks }, [networks])
  useEffect(() => { focusIdxRef.current = focusIdx }, [focusIdx])
  useEffect(() => { busyRef.current = busy }, [busy])
  // Right after off → on NetworkManager has not scanned yet: an empty answer
  // means "not yet" until the next periodic refresh, so the page keeps saying
  // it is scanning without scanning forever where there is no network.
  const radioRef  = useRef<boolean | null | undefined>(undefined)
  const wakingRef = useRef(false)

  /** `tick`: called by the periodic refresh rather than by an action. */
  const refresh = async (tick = false) => {
    try {
      const st = await api.wifi.status()
      setWifiStatus(st)
      const was = radioRef.current
      radioRef.current = st.radio
      if (was === false && st.radio === true) { wakingRef.current = true; setLoading(true) }
      if (st.radio === false) { setNetworks([]); setLoading(false); return }
      const nets = await api.wifi.networks()
      if (wakingRef.current && nets.length === 0 && !tick) return
      wakingRef.current = false
      setNetworks(nets)
    } catch {}
    setLoading(false)
  }

  useEffect(() => { refresh() }, [])
  // Picks up a radio or network change made outside this page.
  useEffect(() => {
    const t = setInterval(() => { if (!busyRef.current && !showKeyboard) refresh(true) }, REFRESH_MS)
    return () => clearInterval(t)
  }, [showKeyboard])

  const hasRadio = typeof wifiStatus?.radio === 'boolean'
  const radioOn  = wifiStatus?.radio === true
  const onEthernet = !!wifiStatus?.ethernet?.connected

  const switchRadio = async () => {
    if (busyRef.current) return
    if (radioOn && !onEthernet && !armed) { setArmed(true); return }
    setArmed(false); setBusy(true); setMsg('')
    try { await api.wifi.setRadio(!radioOn) } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Could not reach the backend.'); setMsgError(true)
    }
    setBusy(false)
    await refresh()
  }
  const switchRef = useRef(switchRadio)
  switchRef.current = switchRadio

  // Off the radio row disarms it; no network to stand on puts the cursor there.
  useEffect(() => { if (focusIdx !== RADIO) setArmed(false) }, [focusIdx])
  useEffect(() => {
    if (hasRadio && !loading && networks.length === 0) setFocusIdx(RADIO)
  }, [hasRadio, loading, networks.length])
  const topRef = useRef(0)
  topRef.current = hasRadio ? RADIO : 0

  useSubPageGamepad(
    showKeyboard ? () => setShowKeyboard(false) : onBack,
    onClose,
    !showKeyboard,
  )

  const handleNetworkRef = useRef<(n: WifiNetwork) => void>(() => {})

  useEffect(() => {
    if (showKeyboard) return
    const offs = [
      onGp('gp:dpad-up',   () => setFocusIdx(i => Math.max(topRef.current, i - 1))),
      onGp('gp:dpad-down', () => setFocusIdx(i => Math.max(topRef.current, Math.min(networksRef.current.length - 1, i + 1)))),
      onGp('gp:confirm',   () => {
        if (busyRef.current) return
        if (focusIdxRef.current === RADIO) { switchRef.current(); return }
        const n = networksRef.current[focusIdxRef.current]
        if (n) handleNetworkRef.current(n)
      }),
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
        setMsg(r.wrong_password ? 'Wrong password. Try again.' : (r.error ?? 'Connection failed'))
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
      <Overlay onClose={onClose} width={560}>
        <BackHeader label="Wi-Fi" onBack={() => setShowKeyboard(false)} />
        <VirtualKeyboard
          title={`Password for "${pendingSsid}"`}
          password
          onConfirm={pwd => doConnect(pendingSsid, pwd)}
          onCancel={() => setShowKeyboard(false)}
        />
      </Overlay>
    )
  }

  const showList = (!onEthernet || showWifiAnyway) && (radioOn || !hasRadio)

  return (
    <Overlay onClose={onClose} width={560}>
      {/* Refresh rides on the header, not above the list.
          In the body it was a lone pill that read as a first list item the
          cursor skipped over — it is a page action, and it belongs on the
          page's title line. */}
      <BackHeader label="Wi-Fi" onBack={onBack} right={showList && (
        <button
          onClick={() => { setLoading(true); refresh() }}
          disabled={busy || loading}
          style={{
            display: 'flex', alignItems: 'center', gap: 7, padding: '7px 13px',
            borderRadius: 9, border: '1px solid rgba(255,255,255,0.1)',
            background: 'rgba(255,255,255,0.05)', color: 'var(--gc-ink-2)',
            fontSize: 15, cursor: busy || loading ? 'default' : 'pointer',
            opacity: busy || loading ? 0.4 : 1,
          }}
        >
          <Glyph name="refresh" size={14} />{loading ? 'Scanning…' : 'Refresh'}
        </button>
      )} />

      {hasRadio && (
        <RadioRow on={radioOn} focused={focusIdx === RADIO} armed={armed}
          note={onEthernet ? 'The cable keeps this box online either way.'
            : radioOn ? 'Turning it off takes this box offline.'
            : 'This box is offline until Wi-Fi is back on.'}
          onClick={() => { setFocusIdx(RADIO); switchRadio() }} />
      )}

      {/* Wired connection — no need for Wi-Fi */}
      {onEthernet && (
        <Banner icon="ethernet" title="Connected via Ethernet"
          sub={`Wired network${wifiStatus?.ethernet.ip ? `, ${wifiStatus.ethernet.ip}` : ''}`
            + `${wifiStatus?.ethernet.iface ? ` on ${wifiStatus.ethernet.iface}` : ''}. Wi-Fi is not needed.`} />
      )}

      {/* Current connection banner */}
      {!onEthernet && wifiStatus?.connected && (
        <Banner icon="check" title={wifiStatus.ssid}
          sub={wifiStatus.ip ? `${wifiStatus.ip} on ${wifiStatus.iface}` : ''}
          action={
            <button
              onClick={doDisconnect}
              disabled={busy}
              style={{ padding: '6px 13px', borderRadius: 8, border: '1px solid rgba(248,113,113,0.4)', background: 'rgba(248,113,113,0.1)', color: '#f87171', fontSize: 15, cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.5 : 1 }}
            >
              Disconnect
            </button>
          } />
      )}

      {/* Status/error message */}
      {msg && (
        <div style={{
          fontSize: 15, marginBottom: 12, padding: '9px 13px', borderRadius: 9,
          background: msgError ? 'rgba(239,68,68,0.08)' : 'rgba(255,255,255,0.04)',
          color: msgError ? '#f87171' : 'var(--gc-accent-soft, #f2a46a)', fontWeight: msgError ? 600 : 400,
        }}>
          {msg}
        </div>
      )}

      {/* On ethernet: hide the Wi-Fi list (not needed) unless asked */}
      {onEthernet && !showWifiAnyway && (radioOn || !hasRadio) && (
        <div
          onClick={() => setShowWifiAnyway(true)}
          style={{ textAlign: 'center', fontSize: 15, color: 'var(--gc-ink-3)', cursor: 'pointer', padding: 8 }}
        >
          Show Wi-Fi networks anyway ›
        </div>
      )}

      {hasRadio && !radioOn && <>
        <div style={{ color: 'var(--gc-ink-3)', fontSize: 15, textAlign: 'center', padding: 20 }}>
          Wi-Fi is off. Turn it on to see the networks in range.
        </div>
        <div style={{ marginTop: 14, textAlign: 'center', fontSize: 14, color: 'var(--gc-ink-3)', }}>
          <PadHints text="✕ Turn on · ○ Back" />
        </div>
      </>}

      {showList && <>
      {/* Network list */}
      {loading && networks.length === 0 && (
        <div style={{ color: 'var(--gc-ink-3)', fontSize: 15, textAlign: 'center', padding: 20 }}>Scanning…</div>
      )}
      {!loading && networks.length === 0 && (
        <div style={{ color: 'var(--gc-ink-3)', fontSize: 15, textAlign: 'center', padding: 20 }}>No networks found</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {networks.map((n, ni) => {
          const on = ni === focusIdx
          return (
            <div
              key={n.ssid}
              onClick={() => { setFocusIdx(ni); if (!busy) handleNetwork(n) }}
              style={{
                // Same 60px rhythm as the settings rows, so a list of networks
                // and a list of settings read as the same kind of thing.
                display: 'flex', alignItems: 'center', gap: 14, padding: '0 15px',
                height: 60, borderRadius: 12, cursor: busy ? 'default' : 'pointer',
                background: on ? 'color-mix(in srgb, var(--gc-accent, #b8501b) 18%, transparent)' : n.connected ? 'rgba(74,222,128,0.06)' : 'rgba(255,255,255,0.04)',
                border: on ? '1px solid color-mix(in srgb, var(--gc-accent, #b8501b) 50%, transparent)' : n.connected ? '1px solid rgba(74,222,128,0.25)' : '1px solid rgba(255,255,255,0.07)',
                opacity: busy && !n.connected ? 0.6 : 1,
                transition: 'all 0.12s',
              }}
            >
              <div style={{
                flexShrink: 0, width: 34, height: 34, borderRadius: 10,
                display: 'grid', placeItems: 'center',
                background: on ? 'color-mix(in srgb, var(--gc-accent, #b8501b) 22%, transparent)' : 'rgba(255,255,255,0.05)',
                color: n.connected ? '#4ade80' : on ? 'var(--gc-accent-bright, #f8cfa9)' : 'rgba(255,255,255,0.45)',
              }}>
                <Glyph name={n.connected ? 'check' : n.secured ? 'lock' : 'unlock'} size={17} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: n.connected ? 700 : 500, color: n.connected ? '#4ade80' : '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {n.ssid}
                </div>
                <div style={{ fontSize: 15, color: 'var(--gc-ink-3)', marginTop: 2 }}>
                  {n.connected ? 'Connected' : n.secured ? 'Secured' : 'Open'}
                </div>
              </div>
              <Bars signal={n.signal} />
            </div>
          )
        })}
      </div>

      <div style={{ marginTop: 14, textAlign: 'center', fontSize: 14, color: 'var(--gc-ink-3)', }}>
        <PadHints text="↑↓ Navigate · ✕ Connect/Disconnect" />
      </div>
      </>}
    </Overlay>
  )
}

/** The radio switch, drawn like the Standby page's toggle row. */
function RadioRow({ on, focused, armed, note, onClick }: {
  on: boolean; focused: boolean; armed: boolean; note: string; onClick: () => void
}) {
  return (
    <div role="switch" aria-checked={on} aria-label="Wi-Fi" onClick={onClick} style={{
      padding: '14px 18px', borderRadius: 12, marginBottom: 14, cursor: 'pointer',
      background: focused ? 'color-mix(in srgb, var(--gc-accent, #b8501b) 15%, transparent)' : 'rgba(255,255,255,0.04)',
      border: focused ? '1px solid color-mix(in srgb, var(--gc-accent, #b8501b) 40%, transparent)' : '1px solid rgba(255,255,255,0.07)',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14,
      transition: 'all 0.15s',
    }}>
      <div>
        <div style={{ fontSize: 15, fontWeight: 600, color: '#fff' }}>
          {armed ? 'Press again to turn Wi-Fi off' : 'Wi-Fi'}
        </div>
        <div style={{ fontSize: 15, color: 'var(--gc-ink-3)', marginTop: 3 }}>{note}</div>
      </div>
      <div style={{
        width: 46, height: 26, borderRadius: 13, position: 'relative', flexShrink: 0, transition: 'background 0.2s',
        background: on ? 'color-mix(in srgb, var(--gc-accent, #b8501b) 80%, transparent)' : 'rgba(255,255,255,0.12)',
      }}>
        <div style={{ position: 'absolute', top: 3, left: on ? 23 : 3, width: 20, height: 20, borderRadius: '50%', background: '#fff', transition: 'left 0.2s' }} />
      </div>
    </div>
  )
}

/** The green strip at the top: what you are on right now, and how to leave it. */
function Banner({ icon, title, sub, action }: {
  icon: string; title: string; sub?: string; action?: ReactNode
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 13,
      padding: '12px 15px', borderRadius: 12, marginBottom: 14,
      background: 'rgba(74,222,128,0.08)', border: '1px solid rgba(74,222,128,0.25)',
    }}>
      <span style={{ color: '#4ade80', display: 'grid', placeItems: 'center' }}>
        <Glyph name={icon} size={20} />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: '#4ade80' }}>{title}</div>
        {sub && <div style={{ fontSize: 14.5, color: 'var(--gc-ink-3)', marginTop: 2 }}>{sub}</div>}
      </div>
      {action}
    </div>
  )
}
