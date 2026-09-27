/**
 * The controller screen's markup — one markup, dressed per theme.
 *
 * Classes only (`gcs-pad-*`, styles in settings/css/gamepad.css), so a theme
 * restyles it from its stylesheet instead of rewriting it: `skin` puts the
 * theme's class on the scrim, `callouts` letters the diagram for a manual
 * page. See gamepad/types.ts for what each prop means.
 */
import type { GamepadViewProps } from './types'
import type { PadInfo } from '../../../lib/padLayout'

const CLASS_LABELS: Record<string, string> = {
  adapter: 'Adapter', wheel: 'Wheel', lightgun: 'Light gun',
  arcade: 'Arcade stick', gamepad: 'Controller', unknown: 'Peripheral',
}

// The manual page's key, in the diagram's letter order (A to K).
const PARTS: [string, string][] = [['l2', 'L2'], ['l1', 'L1'], ['r2', 'R2'], ['r1', 'R1'], ['up', 'D-pad'],
  ['south', 'Face buttons'], ['ls', 'Left stick, click L3'], ['rs', 'Right stick, click R3'],
  ['select', 'Select'], ['start', 'Start'], ['home', 'Home']]

/** "Bluetooth, battery 85%, charging" */
function detail(p: Pick<PadInfo, 'connection' | 'battery' | 'charging'>) {
  return [p.connection, p.battery != null ? `battery ${p.battery}%` : '', p.charging ? 'charging' : '']
    .filter(Boolean).join(', ')
}

export default function DefaultGamepadView({
  pads, pad, status, missing, absent = [], rawButtons = [], actions, Position, usbDevices = [], notice = '',
  onClose, onRemap, Art, skin = 'gcs-skin-default', callouts = false,
}: GamepadViewProps & { skin?: string; callouts?: boolean }) {
  const lost = pad?.raw || pad?.known === 'unknown'
  return (
    <div className={`gcs-pad-scrim ${skin}`} onClick={e => e.target === e.currentTarget && onClose()}>
      <section className="gcs-pad" data-pads={pads.length} data-state={!pad ? 'none' : pad.raw ? 'raw' : 'ok'}>
        <header className="gcs-pad-head">
          <div className="gcs-pad-id">
            <div className="gcs-pad-eyebrow">Controller</div>
            <h2 className="gcs-pad-name">{pad ? pad.name : 'No controller'}</h2>
            {pad && <div className="gcs-pad-sub">{[pad.player ? `Player ${pad.player}` : '', detail(pad)].filter(Boolean).join(', ')}</div>}
          </div>
          {status && <div className="gcs-pad-status" data-tone={status.tone}><i />{status.text}</div>}
        </header>

        {/* Above the diagram: it reads the pad straight from the browser and
            looks perfect whether or not any emulator was configured. */}
        {notice && <div className="gcs-pad-notice">{notice}</div>}

        {!pad ? (
          <div className="gcs-pad-empty">
            <div className="gcs-pad-art" aria-hidden="true"><Art /></div>
            <b>No controller</b>
            <p>Pair one over Bluetooth, or plug it in. It shows here as soon as it wakes.</p>
          </div>
        ) : (
          <div className="gcs-pad-body">
            <div className="gcs-pad-main">
              <div className="gcs-pad-art" aria-hidden="true" data-raw={pad.raw ? '1' : '0'}><Art callouts={callouts} /></div>
              {lost && onRemap && (
                <button className="gcs-pad-map" onClick={onRemap}>
                  <b>Map this pad</b>
                  <span>Hold the top button for a second, or click here. About a minute, no keyboard.</span>
                </button>
              )}
              {rawButtons.length > 0 && (
                <div className="gcs-pad-raw">
                  <p className="gcs-pad-line">The buttons it sends, as it numbers them:</p>
                  <div>{rawButtons.map((on, i) => <span key={i} data-on={on ? '1' : '0'}>B{i + 1}</span>)}</div>
                </div>
              )}
              {missing && <p className="gcs-pad-line">{missing}</p>}
              {!pad.raw && <p className="gcs-pad-line">Press a button: the same spot lights up. Wrong spot, or nothing? Map this pad.</p>}
            </div>

            <aside className="gcs-pad-side">
              {pads.length > 1 && pads.map(p => (
                <div key={p.index} className="gcs-pad-card" data-on={p.active ? '1' : '0'}>
                  <span className="gcs-pad-player">{p.player ? `P${p.player}` : '?'}</span>
                  <span className="gcs-pad-card-text">
                    <b>{p.name}</b>
                    <i>{detail(p)}{p.active && <em>{detail(p) ? ', ' : ''}reading now</em>}</i>
                  </span>
                </div>
              ))}
              {pads.length > 1 && <p className="gcs-pad-hint">Press a button on another pad to read that one.</p>}
              {callouts && (
                <ol className="gcs-pad-key" type="A">
                  {PARTS.map(([c, t]) => absent.includes(c)
                    ? <li key={c} data-gone="1">{t}, not on this pad</li> : <li key={c}>{t}</li>)}
                </ol>
              )}
              {!lost && onRemap && <button className="gcs-pad-remap" onClick={onRemap}>Map this pad</button>}
            </aside>
          </div>
        )}

        {/* Absent is not an error: a box with no GameCube adapter works. A band
            of its own: three adapters' notes in the side column pushed the
            legend and the hints off a 1080p screen. */}
        {usbDevices.length > 0 && (
          <div className="gcs-pad-usbs">
            <div className="gcs-pad-hint">Peripherals</div>
            {usbDevices.map(d => (
              <div key={`${d.system_id}:${d.vid_pid}`} className="gcs-pad-usb" data-present={d.status === 'present' ? '1' : '0'}>
                <div>{d.label}<span>, {CLASS_LABELS[d.class] ?? CLASS_LABELS.unknown}, for {d.system_label}</span></div>
                <b>{d.status === 'present' ? 'Detected' : 'Not detected'}</b>
                {d.status === 'absent' && <p>{d.note}</p>}
              </div>
            ))}
          </div>
        )}

        {pad && !pad.raw && (
          <div className="gcs-pad-actions">
            {actions.map(a => (
              <div key={a.action} className="gcs-pad-action">
                {a.pos ? <><Position pos={a.pos} /><em>{a.label}</em></>
                  : <span>{(a.keys ?? []).map(k => <kbd key={k}>{k}</kbd>)}</span>}
                <span>{a.action}</span>
              </div>
            ))}
          </div>
        )}

        <div className="gcs-pad-hints">
          {pad && <span>Press any button to test it</span>}
          {pad && <span>Hold <Position pos="north" /> top to map this pad</span>}
          <span><Position pos="west" /> left twice to close</span>
        </div>
      </section>
    </div>
  )
}
