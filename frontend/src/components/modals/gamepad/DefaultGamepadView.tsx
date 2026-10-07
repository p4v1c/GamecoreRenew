/**
 * The controller screen's markup: one panel, dressed per theme.
 *
 * Classes only (`gcs-pad-*`, styles in settings/css/gamepad.css), so a theme
 * restyles it from its stylesheet instead of rewriting it: `skin` puts the
 * theme's class on the scrim. The drawing on the left, the quick guide on the
 * right. See gamepad/types.ts for what each prop means.
 */
import type { GamepadViewProps } from './types'
import { useStore } from '../../../store'
import { playerLabel, playerTitle } from '../../../lib/players'

export default function DefaultGamepadView({
  pads, pad, status, missing, rawButtons = [], actions, Position, notice = '',
  onClose, onRemap, Art, skin = 'gcs-skin-default',
}: GamepadViewProps & { skin?: string; callouts?: boolean }) {
  const playerOneName = useStore(s => s.playerOneName)
  const lost = pad?.raw || pad?.known === 'unknown'
  const battery = pad?.battery != null ? ` · ${pad.battery}%${pad.charging ? ' ↯' : ''}` : ''
  return (
    <div className={`gcs-pad-scrim ${skin}`} onClick={e => e.target === e.currentTarget && onClose()}>
      <section className="gcs-pad" role="dialog" aria-modal="true" aria-labelledby="gcs-pad-title"
        data-pads={pads.length} data-state={!pad ? 'none' : pad.raw ? 'raw' : 'ok'}>
        <header className="gcs-pad-head">
          <div>
            <span className="gcs-pad-kicker">GAMECORE / ACCESSORIES</span>
            <h2 id="gcs-pad-title">Your controller<span>.</span></h2>
          </div>
          <button className="gcs-pad-close" onClick={onClose} aria-label="Close controller">✕</button>
        </header>

        {notice && <p className="gcs-pad-notice">{notice}</p>}

        <div className="gcs-pad-body">
          <div className="gcs-pad-main">
            <div className="gcs-pad-meta">
              <span className="gcs-pad-player">{pad ? playerTitle(pad.player || 1, playerOneName).toUpperCase() : 'NOT CONNECTED'}</span>
              <span className="gcs-pad-conn">{pad?.connection}{battery}</span>
            </div>
            <div className="gcs-pad-art" aria-hidden="true" data-empty={!pad || !!pad.raw}><Art /></div>
            <div className="gcs-pad-device">
              <h3>{pad?.name || 'Ready when you are'}</h3>
              <p>{!pad ? 'Connect a controller with Bluetooth or USB.'
                : pad.raw ? 'Press a button to identify its number.' : 'Press any button to see it light up.'}</p>
            </div>
            {status && <div className="gcs-pad-status" data-tone={status.tone}><i />{status.text}</div>}
            {missing && <p className="gcs-pad-note">{missing}</p>}
            {rawButtons.length > 0 && (
              <div className="gcs-pad-raw">
                {rawButtons.map((on, i) => <span key={i} data-on={on ? '1' : '0'}>B{i + 1}</span>)}
              </div>
            )}
          </div>

          <aside className="gcs-pad-guide">
            <span className="gcs-pad-kicker">{lost ? 'SETUP' : 'QUICK GUIDE'}</span>
            <h3>{lost ? 'Make it yours.' : 'Everything in reach.'}</h3>
            {pad && !pad.raw ? (
              <div className="gcs-pad-actions">
                {actions.map(a => (
                  <div className="gcs-pad-action" key={a.action}>
                    {a.pos ? <Position pos={a.pos} size={28} />
                      : <span className="gcs-pad-keys">{a.keys?.map(k => <kbd key={k}>{k}</kbd>)}</span>}
                    <span>{a.action}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="gcs-pad-note">{lost
                ? 'This controller needs a button mapping. Configure it to use it with GameCore.'
                : 'Your shortcuts and live button feedback will appear here once connected.'}</p>
            )}
            {pad && onRemap && (
              <button className="gcs-pad-map" title="Hold the top face button for one second to configure" onClick={onRemap}>
                <span className="gcs-pad-map-copy">
                  {lost ? 'Map this controller' : 'Configure controller'}
                  <small>Hold <Position pos="north" size={12} /> for 1 s to configure</small>
                </span>
                <span aria-hidden="true">↗</span>
              </button>
            )}
            {pads.length > 1 && (
              <div className="gcs-pad-roster">
                {pads.map(p => (
                  <div key={p.index} data-active={p.active ? '1' : '0'}>
                    <b>{p.player ? playerLabel(p.player, playerOneName) : 'P'}</b><span>{p.name}</span><i />
                  </div>
                ))}
                <p>Press a button on another controller to test it.</p>
              </div>
            )}
          </aside>
        </div>

        <footer className="gcs-pad-foot">
          <span><i /> {pad ? 'Live input preview' : 'Waiting for a controller'}</span>
          <span><Position pos="west" size={22} /> Press twice to close</span>
        </footer>
      </section>
    </div>
  )
}
