import { useState, useEffect, useRef } from 'react'
import { Overlay, BackHeader } from '../../ui'
import { api } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { useSubPageGamepad } from './useSubPageGamepad'

const ROWS = ['enabled', 'screensaver', 'sleep'] as const

/** Settings → Standby: enable + the two idle delays (slideshow, screen off). */
export function StandbyPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [enabled, setEnabled] = useState(true)
  const [saverMins, setSaverMins] = useState(10)
  const [sleepMins, setSleepMins] = useState(20)
  const [focus, setFocus] = useState(0)

  const ref = useRef({ enabled, saverMins, sleepMins, focus })
  useEffect(() => { ref.current = { enabled, saverMins, sleepMins, focus } }, [enabled, saverMins, sleepMins, focus])

  useEffect(() => {
    api.standby.get().then(r => {
      setEnabled(r.enabled)
      setSaverMins(r.screensaver_mins)
      setSleepMins(r.sleep_mins)
    }).catch(() => {})
  }, [])

  useSubPageGamepad(onBack, onClose)

  const save = (cfg: { enabled?: boolean; screensaver_mins?: number; sleep_mins?: number }) => {
    api.standby.setConfig(cfg).then(r => {
      setEnabled(r.enabled)
      setSaverMins(r.screensaver_mins)
      setSleepMins(r.sleep_mins)
    }).catch(() => {})
  }

  const adjust = (dir: 1 | -1) => {
    const { focus, saverMins, sleepMins } = ref.current
    if (ROWS[focus] === 'screensaver') save({ screensaver_mins: Math.max(1, Math.min(120, saverMins + dir * 5)) })
    if (ROWS[focus] === 'sleep') save({ sleep_mins: Math.max(1, Math.min(180, sleepMins + dir * 5)) })
  }

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-up',    () => setFocus(i => Math.max(0, i - 1))),
      onGp('gp:dpad-down',  () => setFocus(i => Math.min(ROWS.length - 1, i + 1))),
      onGp('gp:dpad-left',  () => adjust(-1)),
      onGp('gp:dpad-right', () => adjust(1)),
      onGp('gp:confirm',    () => { if (ROWS[ref.current.focus] === 'enabled') save({ enabled: !ref.current.enabled }) }),
    ]
    return () => offs.forEach(o => o())
  }, [])

  const rowStyle = (i: number): React.CSSProperties => ({
    padding: '14px 18px', borderRadius: 12, marginBottom: 10, cursor: 'pointer',
    background: focus === i ? 'color-mix(in srgb, var(--gc-accent, #7c3aed) 15%, transparent)' : 'rgba(255,255,255,0.04)',
    border: focus === i ? '1px solid color-mix(in srgb, var(--gc-accent, #7c3aed) 40%, transparent)' : '1px solid rgba(255,255,255,0.07)',
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    transition: 'all 0.15s',
  })

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="STANDBY" onBack={onBack} />

      <div onClick={() => save({ enabled: !enabled })} style={rowStyle(0)}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#fff' }}>Standby mode</div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.38)', marginTop: 3 }}>
            Slideshow, then screen off when idle — SSH and updates stay active. Any controller button wakes the box.
          </div>
        </div>
        <div style={{
          width: 46, height: 26, borderRadius: 13, position: 'relative', flexShrink: 0, transition: 'background 0.2s',
          background: enabled ? 'color-mix(in srgb, var(--gc-accent, #7c3aed) 80%, transparent)' : 'rgba(255,255,255,0.12)',
        }}>
          <div style={{ position: 'absolute', top: 3, left: enabled ? 23 : 3, width: 20, height: 20, borderRadius: '50%', background: '#fff', transition: 'left 0.2s' }} />
        </div>
      </div>

      <div style={{ opacity: enabled ? 1 : 0.35, pointerEvents: enabled ? 'auto' : 'none', transition: 'opacity 0.2s' }}>
        {([
          ['screensaver', 'Screensaver after', saverMins, 1],
          ['sleep', 'Screen off after', sleepMins, 2],
        ] as const).map(([, label, mins, i]) => (
          <div key={label} style={rowStyle(i)}>
            <div style={{ fontSize: 15, fontWeight: 600, color: '#fff' }}>{label}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <span style={{ color: 'rgba(255,255,255,0.25)', fontSize: 18 }}>‹</span>
              <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--gc-accent-bright, #c4b5fd)', minWidth: 70, textAlign: 'center' }}>{mins} min</span>
              <span style={{ color: 'rgba(255,255,255,0.25)', fontSize: 18 }}>›</span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 12, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        ↑↓ Select · ←→ Adjust · ✕ Toggle · ○ Back
      </div>
    </Overlay>
  )
}
