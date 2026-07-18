import { useState, useEffect, useRef, type CSSProperties } from 'react'
import { Overlay, BackHeader, SliderRow } from '../../ui'
import { api } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { useSubPageGamepad } from './useSubPageGamepad'
import { playSound, soundSettings } from '../../../lib/sounds'

/** Settings → Audio: everything sound-related on one console-style page —
 *  system volume first, then the output picker, then the UI sound effects
 *  (formerly a separate "UI Sounds" page). ↑↓ moves between rows, ←→ adjusts
 *  the focused slider, ✕ applies/toggles the focused row. */
export function AudioPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [volume, setVolumeState] = useState(50)
  const [sinks, setSinks] = useState<{ id: string; name: string; default: boolean }[]>([])
  const [uiEnabled, setUiEnabled] = useState(soundSettings.enabled)
  const [uiVolume, setUiVolume] = useState(soundSettings.volume)
  const [focus, setFocus] = useState(0)
  const [error, setError] = useState('')

  // Row layout: 0 = system volume · 1..sinks = outputs · toggle · UI volume
  const uiToggleIdx = 1 + sinks.length
  const uiVolumeIdx = uiToggleIdx + 1

  const volumeRef = useRef(volume)
  const sinksRef = useRef(sinks)
  const focusRef = useRef(focus)
  const uiEnabledRef = useRef(uiEnabled)
  const uiVolumeRef = useRef(uiVolume)
  useEffect(() => { volumeRef.current = volume }, [volume])
  useEffect(() => { sinksRef.current = sinks }, [sinks])
  useEffect(() => { focusRef.current = focus }, [focus])
  useEffect(() => { uiEnabledRef.current = uiEnabled }, [uiEnabled])
  useEffect(() => { uiVolumeRef.current = uiVolume }, [uiVolume])

  useEffect(() => {
    api.audio.get().then(r => setVolumeState(r.volume)).catch(() => {})
    api.audio.sinks().then(list => setSinks(list)).catch(() => {})
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

  const applyUiEnabled = (v: boolean) => {
    soundSettings.enabled = v
    setUiEnabled(v)
    if (v) playSound('confirm')
  }

  const applyUiVolume = (v: number) => {
    soundSettings.volume = v
    setUiVolume(v)
    playSound('confirm')  // preview at the new volume
  }

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-up',   () => setFocus(i => Math.max(0, i - 1))),
      onGp('gp:dpad-down', () => setFocus(i => Math.min(1 + sinksRef.current.length + 1, i + 1))),
      onGp('gp:dpad-left', () => {
        const f = focusRef.current
        if (f === 0) applyVolume(Math.max(0, volumeRef.current - 5))
        else if (f === 1 + sinksRef.current.length + 1) applyUiVolume(Math.max(0, uiVolumeRef.current - 5))
      }),
      onGp('gp:dpad-right', () => {
        const f = focusRef.current
        if (f === 0) applyVolume(Math.min(100, volumeRef.current + 5))
        else if (f === 1 + sinksRef.current.length + 1) applyUiVolume(Math.min(100, uiVolumeRef.current + 5))
      }),
      onGp('gp:confirm', () => {
        const f = focusRef.current
        const sinkList = sinksRef.current
        if (f >= 1 && f <= sinkList.length) {
          const s = sinkList[f - 1]
          if (s) applySink(s.id)
        } else if (f === 1 + sinkList.length) {
          applyUiEnabled(!uiEnabledRef.current)
        }
      }),
    ]
    return () => offs.forEach(o => o())
  }, [])

  // Focused rows get the same purple outline as the output picker
  const focusWrap = (focused: boolean): CSSProperties => ({
    padding: '0 12px', borderRadius: 10, transition: 'all 0.12s',
    background: focused ? 'rgba(124,58,237,0.12)' : 'transparent',
    border: focused ? '1px solid rgba(124,58,237,0.5)' : '1px solid transparent',
  })

  const sectionTitle: CSSProperties = {
    fontSize: 12, color: 'rgba(255,255,255,0.3)', letterSpacing: 2, margin: '16px 0 8px',
  }

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="AUDIO" onBack={onBack} />

      {/* System volume — the sound that matters most, always on top */}
      <div style={focusWrap(focus === 0)} onClick={() => setFocus(0)}>
        <SliderRow label="System volume" value={volume} onChange={applyVolume} />
      </div>
      {error && (
        <div style={{ fontSize: 12, color: '#f87171', margin: '8px 0', padding: '8px 12px', borderRadius: 8, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
          ⚠ {error}
        </div>
      )}

      {sinks.length > 0 && (
        <>
          <div style={sectionTitle}>OUTPUT</div>
          {sinks.map((s, i) => (
            <div key={s.id} onClick={() => { setFocus(1 + i); applySink(s.id) }} style={{
              padding: '12px 16px', borderRadius: 10, marginBottom: 6, cursor: 'pointer',
              background: focus === 1 + i ? 'rgba(124,58,237,0.2)' : s.default ? 'rgba(124,58,237,0.08)' : 'rgba(255,255,255,0.04)',
              border: focus === 1 + i ? '1px solid rgba(124,58,237,0.6)' : s.default ? '1px solid rgba(124,58,237,0.3)' : '1px solid rgba(255,255,255,0.07)',
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

      <div style={sectionTitle}>UI SOUNDS</div>
      <div onClick={() => { setFocus(uiToggleIdx); applyUiEnabled(!uiEnabled) }} style={{
        padding: '14px 18px', borderRadius: 10, marginBottom: 6, cursor: 'pointer',
        background: focus === uiToggleIdx ? 'rgba(124,58,237,0.2)' : 'rgba(255,255,255,0.04)',
        border: focus === uiToggleIdx ? '1px solid rgba(124,58,237,0.6)' : '1px solid rgba(255,255,255,0.07)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        transition: 'all 0.12s',
      }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#fff' }}>Interface sounds</div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.38)', marginTop: 3 }}>
            Navigation ticks, select and launch chimes
          </div>
        </div>
        {/* Toggle pill */}
        <div style={{
          width: 46, height: 26, borderRadius: 13, position: 'relative', transition: 'background 0.2s',
          background: uiEnabled ? 'rgba(124,58,237,0.8)' : 'rgba(255,255,255,0.12)',
        }}>
          <div style={{
            position: 'absolute', top: 3, left: uiEnabled ? 23 : 3, width: 20, height: 20,
            borderRadius: '50%', background: '#fff', transition: 'left 0.2s',
          }} />
        </div>
      </div>
      <div style={{ opacity: uiEnabled ? 1 : 0.35, pointerEvents: uiEnabled ? 'auto' : 'none', transition: 'opacity 0.2s' }}>
        <div style={focusWrap(focus === uiVolumeIdx)} onClick={() => setFocus(uiVolumeIdx)}>
          <SliderRow label="Sound volume" value={uiVolume} onChange={applyUiVolume} />
        </div>
      </div>

      <div style={{ marginTop: 12, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        ↑↓ Select · ←→ Adjust · ✕ Apply/Toggle · ○ Back
      </div>
    </Overlay>
  )
}
