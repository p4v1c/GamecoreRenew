import { useState, useEffect, useRef, useCallback } from 'react'
import { Overlay, OverlayLabel } from '../ui'
import { useStore } from '../../store'
import { onGp } from '../../hooks/useGamepad'
import { WifiPage }      from './settings/WifiPage'
import { AudioPage }     from './settings/AudioPage'
import { BluetoothPage } from './settings/BluetoothPage'
import { UpdatePage }    from './settings/UpdatePage'
import { DesktopPage }   from './settings/DesktopPage'
import { StandbyPage }   from './settings/StandbyPage'
import { ThemesPage } from './settings/ThemesPage'

interface Props { onClose: () => void }

type Page = 'main' | 'wifi' | 'audio' | 'bluetooth' | 'standby' | 'update' | 'desktop'

const ITEMS = [
  { id: 'wifi',      icon: '📶', label: 'Wi-Fi',       sub: 'Manage networks' },
  { id: 'audio',     icon: '🔊', label: 'Audio',        sub: 'Volume, output & UI sounds' },
  { id: 'bluetooth', icon: '◉',  label: 'Bluetooth',    sub: 'Devices & pairing' },
  { id: 'standby',   icon: '🌙', label: 'Standby',      sub: 'Screensaver & low power' },
  { id: 'themes',    icon: '🎨', label: 'Themes',       sub: 'Change the look of the UI' },
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
  if (page === 'standby')   return <StandbyPage   onClose={onClose} onBack={back} />
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
