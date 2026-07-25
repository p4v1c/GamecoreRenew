import { useState, useEffect } from 'react'
import { useStore } from '../../store'
import { api, SysInfo } from '../../api'
import { onGp, useGamepadState } from '../../hooks/useGamepad'
import { Overlay, OverlayLabel } from '../ui'
import { ControllerBattery } from '../TopBar'
import ControllerArt, { ControllerLayout } from './gamepad/ControllerArt'

// Ported from stremio-web's GamepadModal (□ toggles it there too), redrawn
// to match GameCore's palette and its actual button mappings.

function detectControllerType(): { type: ControllerLayout; name: string } {
  const gp = navigator.getGamepads?.().find(g => g !== null)
  if (!gp) return { type: 'generic', name: 'No controller detected' }
  const id = gp.id.toLowerCase()
  // Sony vendor id 054c — DualShock / DualSense / generic PlayStation
  if (/sony|playstation|dualsense|dualshock|054c/.test(id)) return { type: 'playstation', name: gp.id }
  // Microsoft vendor id 045e — Xbox / XInput (standard mapping mirrors it)
  if (/xbox|microsoft|xinput|045e/.test(id) || gp.mapping === 'standard') return { type: 'xbox', name: gp.id }
  return { type: 'generic', name: gp.id }
}

const GLYPHS: Record<ControllerLayout, { top: string; right: string; bottom: string; left: string; lb: string; rb: string; menu: string; power: string }> = {
  playstation: { top: '△', right: '○', bottom: '✕', left: '□', lb: 'L1', rb: 'R1', menu: 'Options', power: 'Share' },
  xbox:        { top: 'Y', right: 'B', bottom: 'A', left: 'X', lb: 'LB', rb: 'RB', menu: 'Menu',    power: 'View'  },
  generic:     { top: '△', right: '○', bottom: '✕', left: '□', lb: 'L1', rb: 'R1', menu: 'Options', power: 'Share' },
}

export default function GamepadModal({ onClose }: { onClose: () => void }) {
  const { openModal, closeModal } = useStore()
  const [ctrl, setCtrl] = useState(detectControllerType)
  const [sysInfo, setSysInfo] = useState<SysInfo | null>(null)

  // Live button/axis state — drives the drawing below, frame by frame
  const state = useGamepadState()

  // Register / unregister in the modal stack
  useEffect(() => {
    openModal()
    return () => closeModal()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    api.sysinfo().then(setSysInfo).catch(() => {})
    const refresh = () => setCtrl(detectControllerType())
    const offs = [onGp('gp:connected', refresh), onGp('gp:disconnected', refresh)]
    return () => offs.forEach(o => o())
  }, [])

  // No button binding here on purpose: on this screen every press is a test and
  // must only light up its counterpart on the pad. ○ does NOT go back, and
  // leaving takes a double □ — see CONTROLLER_CLOSE_MS in App.tsx.

  const g = GLYPHS[ctrl.type]

  const MAPPINGS: [string, string][] = [
    [`D-Pad / L-stick`, 'Navigate'],
    [g.bottom, 'Select · Play'],
    [g.right, 'Back'],
    [g.top, 'Search games (library)'],
    [g.left, 'This screen'],
    [g.menu, 'Settings'],
    [g.power, 'Power menu'],
    [`${g.lb} / ${g.rb}`, 'Pages · Sorting'],
    ['PS ×2', 'Quit running game'],
  ]

  return (
    <Overlay onClose={onClose} width={640}>
      <OverlayLabel text="CONTROLLER" />

      {/* Connected controller + battery from the backend registry */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 18, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {sysInfo?.controllers?.[0]?.label || sysInfo?.controllers?.[0]?.name || ctrl.name}
          </div>
          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>
            {ctrl.type === 'playstation' ? 'PlayStation layout' : ctrl.type === 'xbox' ? 'Xbox layout' : 'Standard layout'}
          </div>
        </div>
        {sysInfo?.controllers?.map((c, i) => (
          <ControllerBattery key={i} player={c.player} level={c.level} charging={c.charging} />
        ))}
      </div>

      {/* The pad itself — mirrors the real controller in real time */}
      <div style={{ display: 'flex', justifyContent: 'center', margin: '10px 0 20px' }}>
        <ControllerArt layout={ctrl.type} state={state} />
      </div>

      {/* GameCore mappings */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '7px 24px', marginBottom: 14 }}>
        {MAPPINGS.map(([key, action]) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <kbd style={{
              minWidth: 52, textAlign: 'center', padding: '3px 8px', borderRadius: 6,
              background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)',
              fontSize: 11, fontWeight: 700, color: '#c4b5fd', fontFamily: 'inherit',
            }}>{key}</kbd>
            <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)' }}>{action}</span>
          </div>
        ))}
      </div>

      <div style={{ textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        Press any button to test · {g.left} ×2 Close
      </div>
    </Overlay>
  )
}
