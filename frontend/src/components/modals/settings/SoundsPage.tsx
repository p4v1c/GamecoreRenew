import { useState, useEffect, useRef } from 'react'
import { Overlay, BackHeader, SliderRow } from '../../ui'
import { onGp } from '../../../hooks/useGamepad'
import { useSubPageGamepad } from './useSubPageGamepad'
import { playSound, soundSettings } from '../../../lib/sounds'

/** Settings → UI Sounds: enable/disable + volume, with instant preview. */
export function SoundsPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [enabled, setEnabled] = useState(soundSettings.enabled)
  const [volume, setVolume] = useState(soundSettings.volume)

  const enabledRef = useRef(enabled)
  const volumeRef = useRef(volume)
  useEffect(() => { enabledRef.current = enabled }, [enabled])
  useEffect(() => { volumeRef.current = volume }, [volume])

  useSubPageGamepad(onBack, onClose)

  const applyEnabled = (v: boolean) => {
    soundSettings.enabled = v
    setEnabled(v)
    if (v) playSound('confirm')
  }

  const applyVolume = (v: number) => {
    soundSettings.volume = v
    setVolume(v)
    playSound('confirm')  // preview at the new volume
  }

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-right', () => applyVolume(Math.min(100, volumeRef.current + 5))),
      onGp('gp:dpad-left',  () => applyVolume(Math.max(0,   volumeRef.current - 5))),
      onGp('gp:confirm',    () => applyEnabled(!enabledRef.current)),
    ]
    return () => offs.forEach(o => o())
  }, [])

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="UI SOUNDS" onBack={onBack} />

      <div onClick={() => applyEnabled(!enabled)} style={{
        padding: '14px 18px', borderRadius: 12, marginBottom: 14, cursor: 'pointer',
        background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
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
          background: enabled ? 'rgba(124,58,237,0.8)' : 'rgba(255,255,255,0.12)',
        }}>
          <div style={{
            position: 'absolute', top: 3, left: enabled ? 23 : 3, width: 20, height: 20,
            borderRadius: '50%', background: '#fff', transition: 'left 0.2s',
          }} />
        </div>
      </div>

      <div style={{ opacity: enabled ? 1 : 0.35, pointerEvents: enabled ? 'auto' : 'none', transition: 'opacity 0.2s' }}>
        <SliderRow label="Sound volume" value={volume} onChange={applyVolume} />
      </div>

      <div style={{ marginTop: 12, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        ✕ Toggle · ←→ Volume · ○ Back
      </div>
    </Overlay>
  )
}
