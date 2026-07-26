import { useState, useEffect } from 'react'
import { api, SysInfo } from '../../api'
import { onWsEvent } from '../../hooks/useWebSocket'
import logo from '../../assets/logo.png'

interface Props {
  onSettings: () => void
  onPower: () => void
}

export function ControllerBattery({ player, level, charging }: { player?: number | null; level: number; charging?: boolean }) {
  const color = charging ? '#4ade80' : level > 60 ? '#4ade80' : level > 20 ? '#fbbf24' : '#ef4444'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '5px 10px', borderRadius: 7, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
      {/* Gamepad icon */}
      <svg width="14" height="10" viewBox="0 0 14 10" fill="none">
        <rect x="1" y="3" width="12" height="6" rx="3" stroke="rgba(255,255,255,0.4)" strokeWidth="1"/>
        <rect x="4.5" y="1" width="1.2" height="3" rx="0.6" fill="rgba(255,255,255,0.4)"/>
        <rect x="3" y="2.5" width="4.2" height="1.2" rx="0.6" fill="rgba(255,255,255,0.4)"/>
        <circle cx="9.5" cy="6" r="1" fill="rgba(255,255,255,0.35)"/>
      </svg>
      {/* Console-style slot from the backend controller registry */}
      {player != null && (
        <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.45)', fontWeight: 700, fontFamily: 'monospace' }}>
          P{player}
        </span>
      )}
      {/* Battery bar */}
      <div style={{ position: 'relative', width: 24, height: 10, display: 'flex', alignItems: 'center' }}>
        {/* Body */}
        <div style={{ width: 22, height: 10, borderRadius: 2, border: '1px solid rgba(255,255,255,0.25)', overflow: 'hidden', position: 'relative' }}>
          <div style={{ width: `${level}%`, height: '100%', background: color, transition: 'width 0.5s', borderRadius: 1 }} />
        </div>
        {/* Terminal nub */}
        <div style={{ width: 2, height: 5, background: 'rgba(255,255,255,0.25)', borderRadius: '0 1px 1px 0', flexShrink: 0 }} />
      </div>
      <span style={{ fontSize: 11, color, fontWeight: 700, fontFamily: 'monospace', minWidth: 28 }}>
        {charging && '⚡'}{level}%
      </span>
    </div>
  )
}

function TBtn({ icon, label, color, onClick }: { icon: string; label: string; color: string; onClick: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px',
        borderRadius: 8, cursor: 'pointer', border: hovered ? `1px solid ${color}50` : '1px solid transparent',
        background: hovered ? `${color}18` : 'transparent',
        color: hovered ? color : 'rgba(255,255,255,0.45)',
        fontSize: 13, fontWeight: 500, transition: 'all 0.15s',
      }}
    >
      <span>{icon}</span> {label}
    </button>
  )
}

export default function TopBar({ onSettings, onPower }: Props) {
  const [time, setTime] = useState('')
  const [sysInfo, setSysInfo] = useState<SysInfo | null>(null)
  // Kept out of sysInfo on purpose: controller state arrives pushed and must not
  // depend on a successful /api/sysinfo having landed first.
  const [controllers, setControllers] = useState<SysInfo['controllers']>([])

  useEffect(() => {
    const tick = () => setTime(new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }))
    tick()
    const t = setInterval(tick, 10000)
    return () => clearInterval(t)
  }, [])

  // Controller state arrives pushed, not polled. The backend already broadcast
  // gp:connected / gp:disconnected — Toasts listened, this bar did not, so the
  // battery pill could contradict the connection toast for up to 15s.
  //
  // The slow interval that remains is for IP, storage and version only, none of
  // which move quickly. It starts only once a first read succeeded: until then
  // we retry quickly, so a backend that is not up yet does not leave the bar
  // empty for a whole minute.
  useEffect(() => {
    let alive = true
    let slow: ReturnType<typeof setInterval> | null = null
    let retry: ReturnType<typeof setTimeout> | null = null

    const load = async () => {
      try {
        const s = await api.sysinfo()
        if (!alive) return
        setSysInfo(s)
        setControllers(s.controllers || [])
        if (!slow) slow = setInterval(load, 60000)
      } catch {
        if (alive && !slow) retry = setTimeout(load, 3000)
      }
    }
    load()

    const offs = [
      // A pad appeared or vanished: re-read once, now, instead of waiting.
      onWsEvent('gp:connected', load),
      onWsEvent('gp:disconnected', load),
      // Level or charging changed: the payload is what we render, so no
      // round-trip at all — and no dependency on sysInfo being loaded.
      onWsEvent('gp:controllers', (d) => {
        const list = (d as { controllers?: SysInfo['controllers'] })?.controllers
        if (list) setControllers(list)
      }),
    ]
    return () => {
      alive = false
      if (slow) clearInterval(slow)
      if (retry) clearTimeout(retry)
      offs.forEach(off => off())
    }
  }, [])

  const usedPct = sysInfo ? Math.round((sysInfo.storage_used_gb / sysInfo.storage_total_gb) * 100) : 0
  const barColor = usedPct > 85 ? '#ef4444' : usedPct > 65 ? '#fbbf24' : '#a78bfa'

  return (
    <div style={{
      position: 'relative', zIndex: 20, display: 'flex', alignItems: 'center',
      padding: '0 24px', height: 54, flexShrink: 0,
      background: 'rgba(9,9,15,0.7)', backdropFilter: 'blur(20px)',
      borderBottom: '1px solid rgba(255,255,255,0.06)', gap: 16,
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexShrink: 0 }}>
        <img src={logo} alt="" style={{
          width: 30, height: 30, objectFit: 'contain',
          filter: 'drop-shadow(0 0 8px rgba(124,58,237,0.45))',
        }} />
        <span style={{ fontSize: 16, fontWeight: 900, letterSpacing: -0.5 }}>GAMECORE</span>
      </div>

      <div style={{ flex: 1 }} />

      {/* Sysinfo pills */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {sysInfo && (
          <>
            {/* IP */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px', borderRadius: 7, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
              <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace' }}>{sysInfo.ip}</span>
            </div>

            {/* Storage */}
            <div style={{ padding: '5px 10px', borderRadius: 7, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
              <div style={{ width: 60, height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.1)' }}>
                <div style={{ width: `${usedPct}%`, height: '100%', borderRadius: 2, background: barColor, transition: 'width 0.3s' }} />
              </div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', marginTop: 3 }}>
                {sysInfo.storage_used_gb}G / {sysInfo.storage_total_gb}G
              </div>
            </div>

            {/* Controller batteries */}
            {controllers?.map((c, i) => (
              <ControllerBattery key={i} player={c.player} level={c.level} charging={c.charging} />
            ))}
          </>
        )}

        <div style={{ width: 1, height: 20, background: 'rgba(255,255,255,0.08)' }} />
        <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.3)', fontWeight: 500 }}>{time}</span>
        <TBtn icon="⚙" label="Settings" color="#7c3aed" onClick={onSettings} />
        <TBtn icon="⏻" label="Power" color="#ef4444" onClick={onPower} />
      </div>
    </div>
  )
}
