/**
 * The default controller screen's markup — and nothing else.
 * See gamepad/types.ts.
 */
import { Overlay, OverlayLabel } from '../../ui'
import type { GamepadViewProps } from './types'

const CLASS_LABELS: Record<string, string> = {
  adapter: 'Adapter',
  wheel: 'Wheel',
  lightgun: 'Light gun',
  arcade: 'Arcade stick',
  gamepad: 'Controller',
  unknown: 'Peripheral',
}

export default function DefaultGamepadView({
  name, layoutLabel, controllers, usbDevices = [], glyphs, mappings, onClose, onRemap, Art, Battery,
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

      {/* The peripherals that take no player slot. Nothing is drawn when no
          installed system declares one, which is most boxes — an empty
          "Peripherals" heading is a question the owner did not ask.

          Absent is not an error and must not be red: a box with no GameCube
          adapter is a perfectly working box, and colouring it as a fault is
          exactly the manufactured ticket the BIOS screen documents. The note
          only appears on the absent ones, because that is when there is
          something to check. */}
      {usbDevices.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 10, letterSpacing: 1, color: 'rgba(255,255,255,0.3)', marginBottom: 7 }}>
            PERIPHERALS
          </div>
          {usbDevices.map(d => (
            <div key={`${d.system_id}:${d.vid_pid}`} style={{
              display: 'flex', alignItems: 'baseline', gap: 8, padding: '5px 0',
              borderTop: '1px solid rgba(255,255,255,0.06)',
            }}>
              <span style={{
                width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                alignSelf: 'center',
                background: d.status === 'present' ? '#4ade80' : 'rgba(255,255,255,0.2)',
              }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, color: '#fff' }}>
                  {d.label}
                  <span style={{ color: 'rgba(255,255,255,0.3)', fontWeight: 400 }}>
                    {' · '}{CLASS_LABELS[d.class] ?? CLASS_LABELS.unknown}{' · '}{d.system_label}
                  </span>
                </div>
                {d.status === 'absent' && (
                  <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>
                    {d.note}
                  </div>
                )}
              </div>
              <span style={{
                fontSize: 10, flexShrink: 0,
                color: d.status === 'present' ? '#4ade80' : 'rgba(255,255,255,0.3)',
              }}>
                {d.status === 'present' ? 'Detected' : 'Not detected'}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* The way out for a pad none of the above applies to. A controller SDL
          cannot name lights nothing up in the diagram and matches none of the
          bindings listed, so this screen is exactly where its owner ends up —
          and until now it told them nothing they could act on. */}
      {onRemap && (
        <button onClick={onRemap} style={{
          display: 'block', width: '100%', padding: '10px 14px', marginBottom: 12,
          borderRadius: 10, background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.12)', color: '#fff',
          fontSize: 12, fontWeight: 700, cursor: 'pointer', font: 'inherit',
        }}>
          Buttons wrong or dead? — map this controller
          <span style={{ display: 'block', fontSize: 10, fontWeight: 400, marginTop: 3, color: 'rgba(255,255,255,0.4)' }}>
            Hold {glyphs.top}, or click here. About a minute, no keyboard.
          </span>
        </button>
      )}

      <div style={{ textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        Press any button to test · Hold {glyphs.top} to remap · {glyphs.left} ×2 Close
      </div>
    </Overlay>
  )
}
