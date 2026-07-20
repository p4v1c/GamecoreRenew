import { useState, useEffect } from 'react'
import { useStore } from '../../store'
import { api, SysInfo } from '../../api'
import { onGp } from '../../hooks/useGamepad'
import { Overlay, OverlayLabel } from '../ui'
import { ControllerBattery } from '../TopBar'

// Ported from stremio-web's GamepadModal (□ toggles it there too), redrawn
// to match GameCore's palette and its actual button mappings.

type ControllerType = 'playstation' | 'xbox' | 'generic'

function detectControllerType(): { type: ControllerType; name: string } {
  const gp = navigator.getGamepads?.().find(g => g !== null)
  if (!gp) return { type: 'generic', name: 'No controller detected' }
  const id = gp.id.toLowerCase()
  // Sony vendor id 054c — DualShock / DualSense / generic PlayStation
  if (/sony|playstation|dualsense|dualshock|054c/.test(id)) return { type: 'playstation', name: gp.id }
  // Microsoft vendor id 045e — Xbox / XInput (standard mapping mirrors it)
  if (/xbox|microsoft|xinput|045e/.test(id) || gp.mapping === 'standard') return { type: 'xbox', name: gp.id }
  return { type: 'generic', name: gp.id }
}

const GLYPHS: Record<ControllerType, { top: string; right: string; bottom: string; left: string; lb: string; rb: string; lt: string; rt: string; menu: string; power: string }> = {
  playstation: { top: '△', right: '○', bottom: '✕', left: '□', lb: 'L1', rb: 'R1', lt: 'L2', rt: 'R2', menu: 'Options', power: 'Share' },
  xbox:        { top: 'Y', right: 'B', bottom: 'A', left: 'X', lb: 'LB', rb: 'RB', lt: 'LT', rt: 'RT', menu: 'Menu',    power: 'View'  },
  generic:     { top: '△', right: '○', bottom: '✕', left: '□', lb: 'L1', rb: 'R1', lt: 'L2', rt: 'R2', menu: 'Options', power: 'Share' },
}

export default function GamepadModal({ onClose }: { onClose: () => void }) {
  const { openModal, closeModal } = useStore()
  const [ctrl, setCtrl] = useState(detectControllerType)
  const [sysInfo, setSysInfo] = useState<SysInfo | null>(null)
  const [active, setActive] = useState<string | null>(null)

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

  // Live diagram: every press lights the matching control for 400ms
  useEffect(() => {
    let timeout: ReturnType<typeof setTimeout>
    const flash = (part: string) => () => {
      setActive(part)
      clearTimeout(timeout)
      timeout = setTimeout(() => setActive(null), 400)
    }
    const offs = [
      onGp('gp:dpad-up',    flash('nav')),
      onGp('gp:dpad-down',  flash('nav')),
      onGp('gp:dpad-left',  flash('nav')),
      onGp('gp:dpad-right', flash('nav')),
      onGp('gp:confirm',    flash('bottom')),
      onGp('gp:y',          flash('top')),
      onGp('gp:x',          flash('left')),
      onGp('gp:l1',         flash('lb')),
      onGp('gp:r1',         flash('rb')),
      onGp('gp:l2',         flash('lt')),
      onGp('gp:r2',         flash('rt')),
      // Blocked from opening anything while this modal is on screen — flash only
      onGp('gp:menu',       flash('menu')),
      onGp('gp:power',      flash('power')),
      onGp('gp:back',       onClose),
    ]
    return () => { clearTimeout(timeout); offs.forEach(o => o()) }
  }, [onClose])

  const g = GLYPHS[ctrl.type]
  const isXbox = ctrl.type === 'xbox'
  const hi = (id: string) => active === id
  const stroke = (id: string) => hi(id) ? '#7c3aed' : 'rgba(255,255,255,0.18)'
  const fill = (id: string) => hi(id) ? 'rgba(124,58,237,0.45)' : 'rgba(255,255,255,0.04)'
  const text = (id: string) => hi(id) ? '#fff' : 'rgba(255,255,255,0.55)'

  // PS: sticks side by side low, d-pad upper-left. Xbox: left stick upper-left,
  // d-pad drops low — same asymmetry stremio-web draws.
  const lstick = isXbox ? { x: 100, y: 92 } : { x: 152, y: 148 }
  const dpad   = isXbox ? { x: 152, y: 148 } : { x: 100, y: 92 }

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

      {/* Diagram — press any button to light it up */}
      <svg viewBox="0 0 560 260" style={{ width: '100%', display: 'block', marginBottom: 16 }} xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="gcBody" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#181824" />
            <stop offset="100%" stopColor="#0d0d16" />
          </linearGradient>
        </defs>

        {/* Triggers */}
        {[{ x: 130, id: 'lt', label: g.lt }, { x: 430, id: 'rt', label: g.rt }].map(t => (
          <g key={t.id}>
            <path d={`M${t.x - 30},26 Q${t.x - 32},10 ${t.x - 20},6 L${t.x + 20},6 Q${t.x + 32},10 ${t.x + 30},26 Z`}
              fill={fill(t.id)} stroke={stroke(t.id)} strokeWidth="1.2" />
            <text x={t.x} y="19" textAnchor="middle" fill={text(t.id)} fontSize="9" fontWeight="600">{t.label}</text>
          </g>
        ))}
        {/* Bumpers */}
        {[{ x: 130, id: 'lb', label: g.lb }, { x: 430, id: 'rb', label: g.rb }].map(b => (
          <g key={b.id}>
            <rect x={b.x - 34} y="30" rx="6" width="68" height="16" fill={fill(b.id)} stroke={stroke(b.id)} strokeWidth="1.2" />
            <text x={b.x} y="41.5" textAnchor="middle" fill={text(b.id)} fontSize="9" fontWeight="600">{b.label}</text>
          </g>
        ))}

        {/* Body */}
        <path d={`M110,58 Q130,48 200,46 L360,46 Q430,48 450,58
                  Q505,78 520,150 Q528,200 505,222 Q480,240 458,224
                  L420,190 Q400,172 280,172 Q160,172 140,190 L102,224
                  Q80,240 55,222 Q32,200 40,150 Q55,78 110,58 Z`}
          fill="url(#gcBody)" stroke="rgba(255,255,255,0.12)" strokeWidth="1.5" />

        {/* Options / Share pills */}
        <g>
          <rect x="238" y="66" rx="5" width="38" height="11" fill={fill('power')} stroke={stroke('power')} strokeWidth="1" />
          <text x="257" y="74.5" textAnchor="middle" fill={text('power')} fontSize="6.5">{g.power}</text>
        </g>
        <g>
          <rect x="284" y="66" rx="5" width="38" height="11" fill={fill('menu')} stroke={stroke('menu')} strokeWidth="1" />
          <text x="303" y="74.5" textAnchor="middle" fill={text('menu')} fontSize="6.5">{g.menu}</text>
        </g>

        {/* Face buttons (right cluster) */}
        {[
          { dx: 0,   dy: -22, id: 'top',    glyph: g.top },
          { dx: 22,  dy: 0,   id: 'right',  glyph: g.right },
          { dx: 0,   dy: 22,  id: 'bottom', glyph: g.bottom },
          { dx: -22, dy: 0,   id: 'left',   glyph: g.left },
        ].map(b => (
          <g key={b.id}>
            <circle cx={460 + b.dx - 22} cy={92 + b.dy} r="12"
              fill={b.id === 'bottom' && !active ? 'rgba(124,58,237,0.3)' : fill(b.id)}
              stroke={stroke(b.id)} strokeWidth="1.3" />
            <text x={460 + b.dx - 22} y={96 + b.dy} textAnchor="middle" fill={text(b.id)}
              fontSize={isXbox ? 9 : 10} fontWeight={isXbox ? 700 : 400}>{b.glyph}</text>
          </g>
        ))}

        {/* D-pad */}
        <g>
          <rect x={dpad.x - 8} y={dpad.y - 22} rx="2.5" width="16" height="44" fill={fill('nav')} stroke={stroke('nav')} strokeWidth="1" />
          <rect x={dpad.x - 22} y={dpad.y - 8} rx="2.5" width="44" height="16" fill={fill('nav')} stroke={stroke('nav')} strokeWidth="1" />
        </g>

        {/* Sticks */}
        <g>
          <circle cx={lstick.x} cy={lstick.y} r="19" fill={fill('nav')} stroke={stroke('nav')} strokeWidth="1.5" />
          <circle cx={lstick.x} cy={lstick.y} r="12" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.15)" strokeWidth="1" />
        </g>
        <g>
          <circle cx="386" cy="148" r="19" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.12)" strokeWidth="1.5" />
          <circle cx="386" cy="148" r="12" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.15)" strokeWidth="1" />
        </g>

        {/* PS / guide button */}
        <circle cx="280" cy="120" r="10" fill="rgba(124,58,237,0.18)" stroke="rgba(124,58,237,0.5)" strokeWidth="1.2" />
        <text x="280" y="123.5" textAnchor="middle" fill="#c4b5fd" fontSize="7" fontWeight="700">PS</text>
      </svg>

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
        Press any button to test · □ / ○ Close
      </div>
    </Overlay>
  )
}
