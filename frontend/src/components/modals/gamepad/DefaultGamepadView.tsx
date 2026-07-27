/**
 * The default controller screen's markup — and nothing else.
 * See gamepad/types.ts.
 */
import { Overlay, OverlayLabel } from '../../ui'
import type { GamepadViewProps } from './types'

export default function DefaultGamepadView({
  name, layoutLabel, controllers, glyphs, mappings, onClose, Art, Battery,
}: GamepadViewProps) {
  return (
    <Overlay onClose={onClose} width={640}>
      <OverlayLabel text="CONTROLLER" />

      {/* Connected controller + battery from the backend registry */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 18, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {name}
          </div>
          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>
            {layoutLabel}
          </div>
        </div>
        {controllers.map((c, i) => (
          <Battery key={i} player={c.player} level={c.level} charging={c.charging} />
        ))}
      </div>

      {/* The pad itself — mirrors the real controller in real time */}
      <div style={{ display: 'flex', justifyContent: 'center', margin: '10px 0 20px' }}>
        <Art />
      </div>

      {/* GameCore mappings */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '7px 24px', marginBottom: 14 }}>
        {mappings.map(([key, action]) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <kbd style={{
              minWidth: 52, textAlign: 'center', padding: '3px 8px', borderRadius: 6,
              background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)',
              fontSize: 11, fontWeight: 700, color: 'var(--gc-accent-bright, #c4b5fd)', fontFamily: 'inherit',
            }}>{key}</kbd>
            <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)' }}>{action}</span>
          </div>
        ))}
      </div>

      <div style={{ textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        Press any button to test · {glyphs.left} ×2 Close
      </div>
    </Overlay>
  )
}
