import { useState, useEffect, useRef } from 'react'
import { Overlay, BackHeader, SliderRow } from '../../ui'
import { api } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { useSubPageGamepad } from './useSubPageGamepad'

export function AudioPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
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
