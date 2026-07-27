import { useState, useEffect, useCallback } from 'react'
import { useStore } from '../../store'
import { api, SysInfo } from '../../api'
import { onGp, useGamepadState } from '../../hooks/useGamepad'
import { ControllerBattery } from '../TopBar'
import ControllerArt, { ControllerLayout } from './gamepad/ControllerArt'
import DefaultGamepadView from './gamepad/DefaultGamepadView'
import type { GamepadViewProps } from './gamepad/types'

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

export default function GamepadModal({ onClose, view: View = DefaultGamepadView }: {
  onClose: () => void
  view?: React.ComponentType<GamepadViewProps>
}) {
  const { openModal, closeModal } = useStore()
  const [ctrl, setCtrl] = useState(detectControllerType)
  const [sysInfo, setSysInfo] = useState<SysInfo | null>(null)

  // Live button/axis state — drives the drawing below, frame by frame
  const state = useGamepadState()

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

  // Bound here so a view mounts it with no props and cannot mis-wire the pad.
  const Art = useCallback(() => <ControllerArt layout={ctrl.type} state={state} />, [ctrl.type, state])

  return (
    <View
      layout={ctrl.type}
      name={sysInfo?.controllers?.[0]?.label || sysInfo?.controllers?.[0]?.name || ctrl.name}
      layoutLabel={
        ctrl.type === 'playstation' ? 'PlayStation layout'
        : ctrl.type === 'xbox' ? 'Xbox layout'
        : 'Standard layout'
      }
      connected={ctrl.name !== 'No controller detected'}
      controllers={sysInfo?.controllers ?? []}
      glyphs={g}
      mappings={MAPPINGS}
      onClose={onClose}
      Art={Art}
      Battery={ControllerBattery}
    />
  )
}
