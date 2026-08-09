import { useState, useEffect, useRef, type CSSProperties } from 'react'
import { Overlay, BackHeader, SliderRow } from '../../ui'
import { api } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { useSubPageGamepad } from './useSubPageGamepad'
import { playSound, soundSettings } from '../../../lib/sounds'
import { rumble, rumbleSettings } from '../../../lib/rumble'

// Fixed row layout — the output picker is a single dropdown row
const ROW_VOLUME = 0
const ROW_OUTPUT = 1
const ROW_UI_TOGGLE = 2
const ROW_UI_VOLUME = 3
// Haptics live on the Audio page rather than the controller screen, which is
// where someone would look first. That screen is a live button test — every
// button has to stay free in there, so it cannot carry a toggle. This page is
// already the one that owns feedback rather than output: UI sounds are not
// "audio" either.
const ROW_RUMBLE = 4
const ROW_COUNT = 5

/** Settings → Audio: everything sound-related on one console-style page —
 *  system volume first, an Output dropdown, then the UI sound effects.
 *  ↑↓ moves between rows, ←→ adjusts the focused slider, ✕ opens the
 *  dropdown / applies / toggles; while the dropdown is open, ↑↓ browses the
 *  outputs and ○ closes it without leaving the page. */
export function AudioPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [volume, setVolumeState] = useState(50)
  const [sinks, setSinks] = useState<{ id: string; name: string; default: boolean }[]>([])
  const [uiEnabled, setUiEnabled] = useState(soundSettings.enabled)
  const [uiVolume, setUiVolume] = useState(soundSettings.volume)
  const [rumbleOn, setRumbleOn] = useState(rumbleSettings.enabled)
  const [focus, setFocus] = useState(0)
  const [outputOpen, setOutputOpen] = useState(false)
  const [dropFocus, setDropFocus] = useState(0)
  const [error, setError] = useState('')

  const volumeRef = useRef(volume)
  const sinksRef = useRef(sinks)
  const focusRef = useRef(focus)
  const uiEnabledRef = useRef(uiEnabled)
  const uiVolumeRef = useRef(uiVolume)
  const rumbleOnRef = useRef(rumbleOn)
  const outputOpenRef = useRef(outputOpen)
  const dropFocusRef = useRef(dropFocus)
  useEffect(() => { volumeRef.current = volume }, [volume])
  useEffect(() => { sinksRef.current = sinks }, [sinks])
  useEffect(() => { focusRef.current = focus }, [focus])
  useEffect(() => { uiEnabledRef.current = uiEnabled }, [uiEnabled])
  useEffect(() => { uiVolumeRef.current = uiVolume }, [uiVolume])
  useEffect(() => { rumbleOnRef.current = rumbleOn }, [rumbleOn])
  useEffect(() => { outputOpenRef.current = outputOpen }, [outputOpen])
  useEffect(() => { dropFocusRef.current = dropFocus }, [dropFocus])

  useEffect(() => {
    api.audio.get().then(r => setVolumeState(r.volume)).catch(() => {})
    api.audio.sinks().then(list => setSinks(list)).catch(() => {})
  }, [])

  // While the dropdown is open, B closes it instead of leaving the page
  useSubPageGamepad(onBack, onClose, !outputOpen)

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

  const applyRumble = (v: boolean) => {
    rumbleSettings.enabled = v
    setRumbleOn(v)
    // Preview, and the only way to find out whether this pad can do it at all:
    // most controllers expose no actuator through Chromium, and a toggle that
    // silently governs nothing is worse than no toggle.
    if (v) rumble({ duration: 120, strong: 0.5, weak: 0.3 })
  }

  const openOutput = () => {
    const list = sinksRef.current
    if (list.length === 0) return
    const defIdx = list.findIndex(s => s.default)
    setDropFocus(defIdx >= 0 ? defIdx : 0)
    setOutputOpen(true)
  }

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-up', () => {
        if (outputOpenRef.current) setDropFocus(i => Math.max(0, i - 1))
        else setFocus(i => Math.max(0, i - 1))
      }),
      onGp('gp:dpad-down', () => {
        if (outputOpenRef.current) setDropFocus(i => Math.min(sinksRef.current.length - 1, i + 1))
        else setFocus(i => Math.min(ROW_COUNT - 1, i + 1))
      }),
      onGp('gp:dpad-left', () => {
        if (outputOpenRef.current) return
        const f = focusRef.current
        if (f === ROW_VOLUME) applyVolume(Math.max(0, volumeRef.current - 5))
        else if (f === ROW_UI_VOLUME) applyUiVolume(Math.max(0, uiVolumeRef.current - 5))
      }),
      onGp('gp:dpad-right', () => {
        if (outputOpenRef.current) return
        const f = focusRef.current
        if (f === ROW_VOLUME) applyVolume(Math.min(100, volumeRef.current + 5))
        else if (f === ROW_UI_VOLUME) applyUiVolume(Math.min(100, uiVolumeRef.current + 5))
      }),
      onGp('gp:confirm', () => {
        if (outputOpenRef.current) {
          const s = sinksRef.current[dropFocusRef.current]
          if (s) applySink(s.id)
          setOutputOpen(false)
          return
        }
        const f = focusRef.current
        if (f === ROW_OUTPUT) openOutput()
        else if (f === ROW_UI_TOGGLE) applyUiEnabled(!uiEnabledRef.current)
        else if (f === ROW_RUMBLE) applyRumble(!rumbleOnRef.current)
      }),
    ]
    return () => offs.forEach(o => o())
  }, [])

  useEffect(() => {
    if (!outputOpen) return
    const off = onGp('gp:back', () => setOutputOpen(false))
    return off
  }, [outputOpen])

  const activeSink = sinks.find(s => s.default)

  // Focused rows get the same purple outline as the row cards
  const focusWrap = (focused: boolean): CSSProperties => ({
    padding: '0 12px', borderRadius: 10, transition: 'all 0.12s',
    background: focused ? 'color-mix(in srgb, var(--gc-accent, #7c3aed) 12%, transparent)' : 'transparent',
    border: focused ? '1px solid color-mix(in srgb, var(--gc-accent, #7c3aed) 50%, transparent)' : '1px solid transparent',
  })

  const rowCard = (focused: boolean): CSSProperties => ({
    padding: '14px 18px', borderRadius: 10, marginBottom: 6, cursor: 'pointer',
    background: focused ? 'color-mix(in srgb, var(--gc-accent, #7c3aed) 20%, transparent)' : 'rgba(255,255,255,0.04)',
    border: focused ? '1px solid color-mix(in srgb, var(--gc-accent, #7c3aed) 60%, transparent)' : '1px solid rgba(255,255,255,0.07)',
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    transition: 'all 0.12s',
  })

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="AUDIO" onBack={onBack} />

      {/* System volume — the sound that matters most, always on top */}
      <div style={focusWrap(focus === ROW_VOLUME)} onClick={() => setFocus(ROW_VOLUME)}>
        <SliderRow label="System volume" value={volume} onChange={applyVolume} />
      </div>
      {error && (
        <div style={{ fontSize: 12, color: '#f87171', margin: '8px 0', padding: '8px 12px', borderRadius: 8, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
          ⚠ {error}
        </div>
      )}

      {/* Output — one dropdown row, console-style */}
      <div style={{ ...rowCard(focus === ROW_OUTPUT), marginTop: 10 }}
        onClick={() => { setFocus(ROW_OUTPUT); if (outputOpen) setOutputOpen(false); else openOutput() }}>
        <div style={{ fontSize: 15, fontWeight: 600, color: '#fff' }}>Output</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <span style={{
            fontSize: 13, color: 'rgba(255,255,255,0.55)', maxWidth: 260,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {activeSink ? activeSink.name : sinks.length === 0 ? 'No output found' : '—'}
          </span>
          <span style={{
            fontSize: 11, color: 'rgba(255,255,255,0.4)', transition: 'transform 0.15s',
            transform: outputOpen ? 'rotate(180deg)' : 'none',
          }}>▼</span>
        </div>
      </div>
      {outputOpen && (
        <div style={{
          margin: '0 0 6px 14px', padding: 6, borderRadius: 10,
          background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)',
        }}>
          {sinks.map((s, i) => (
            <div key={s.id} onClick={() => { applySink(s.id); setOutputOpen(false) }} style={{
              padding: '10px 14px', borderRadius: 8, cursor: 'pointer',
              background: i === dropFocus ? 'color-mix(in srgb, var(--gc-accent, #7c3aed) 25%, transparent)' : 'transparent',
              border: i === dropFocus ? '1px solid color-mix(in srgb, var(--gc-accent, #7c3aed) 60%, transparent)' : '1px solid transparent',
              fontSize: 13, color: '#fff',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              transition: 'all 0.12s',
            }}>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</span>
              {s.default && <span style={{ fontSize: 11, color: 'var(--gc-accent-soft, #a78bfa)', fontWeight: 600, marginLeft: 10, flexShrink: 0 }}>Active</span>}
            </div>
          ))}
        </div>
      )}

      {/* UI sound effects */}
      <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', letterSpacing: 2, margin: '16px 0 8px' }}>UI SOUNDS</div>
      <div style={rowCard(focus === ROW_UI_TOGGLE)}
        onClick={() => { setFocus(ROW_UI_TOGGLE); applyUiEnabled(!uiEnabled) }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#fff' }}>Interface sounds</div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.38)', marginTop: 3 }}>
            Navigation ticks, select and launch chimes
          </div>
        </div>
        {/* Toggle pill */}
        <div style={{
          width: 46, height: 26, borderRadius: 13, position: 'relative', transition: 'background 0.2s',
          background: uiEnabled ? 'color-mix(in srgb, var(--gc-accent, #7c3aed) 80%, transparent)' : 'rgba(255,255,255,0.12)', flexShrink: 0,
        }}>
          <div style={{
            position: 'absolute', top: 3, left: uiEnabled ? 23 : 3, width: 20, height: 20,
            borderRadius: '50%', background: '#fff', transition: 'left 0.2s',
          }} />
        </div>
      </div>
      <div style={{ opacity: uiEnabled ? 1 : 0.35, pointerEvents: uiEnabled ? 'auto' : 'none', transition: 'opacity 0.2s' }}>
        <div style={focusWrap(focus === ROW_UI_VOLUME)} onClick={() => setFocus(ROW_UI_VOLUME)}>
          <SliderRow label="Sound volume" value={uiVolume} onChange={applyUiVolume} />
        </div>
      </div>

      {/* Haptics */}
      <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', letterSpacing: 2, margin: '16px 0 8px' }}>HAPTICS</div>
      <div style={rowCard(focus === ROW_RUMBLE)}
        onClick={() => { setFocus(ROW_RUMBLE); applyRumble(!rumbleOn) }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#fff' }}>Controller vibration</div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.38)', marginTop: 3 }}>
            Only themes that ask for it — nothing vibrates by default
          </div>
        </div>
        <div style={{
          width: 46, height: 26, borderRadius: 13, position: 'relative', transition: 'background 0.2s',
          background: rumbleOn ? 'color-mix(in srgb, var(--gc-accent, #7c3aed) 80%, transparent)' : 'rgba(255,255,255,0.12)', flexShrink: 0,
        }}>
          <div style={{
            position: 'absolute', top: 3, left: rumbleOn ? 23 : 3, width: 20, height: 20,
            borderRadius: '50%', background: '#fff', transition: 'left 0.2s',
          }} />
        </div>
      </div>

      <div style={{ marginTop: 12, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        {outputOpen ? '↑↓ Browse outputs · ✕ Apply · ○ Close' : '↑↓ Select · ←→ Adjust · ✕ Open/Toggle · ○ Back'}
      </div>
    </Overlay>
  )
}
