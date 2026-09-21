import { useEffect } from 'react'
import { useStore } from '../../store'
import { onGp } from '../../hooks/useGamepad'
import { formatGameName } from '../../lib/formatGameName'
import { Overlay } from '../ui'

const titleOf = (key: string) => formatGameName(
  key.replace(/\.[^.]+$/, '').replace(/[_]+/g, ' '),
)

/** Host-owned so every launch surface gets the same rule and every theme gets
 * the dialog in its own `--gc-overlay-*` palette. */
export default function LaunchConflictModal() {
  const conflict = useStore(s => s.launchConflict)
  const dismiss = () => useStore.getState().setLaunchConflict(null)

  useEffect(() => {
    if (!conflict) return
    const offs = [onGp('gp:confirm', dismiss), onGp('gp:back', dismiss)]
    return () => offs.forEach(off => off())
  }, [conflict?.session]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!conflict) return null
  const title = titleOf(conflict.gameKey)
  return (
    <Overlay onClose={dismiss} width={520}>
      <div className="launch-conflict-dialog" role="alertdialog"
           aria-labelledby="launch-conflict-title"
           aria-describedby="launch-conflict-description">
        <div style={{ fontSize: 10, letterSpacing: 2.5, opacity: 0.55, marginBottom: 16 }}>
          GAME STILL RUNNING
        </div>
        <h2 id="launch-conflict-title" style={{ fontSize: 28, margin: '0 0 14px' }}>
          Another game is still running
        </h2>
        <p id="launch-conflict-description" style={{ lineHeight: 1.65, opacity: 0.72, margin: 0 }}>
          Close <strong style={{ color: '#fff' }}>{title}</strong> before starting a different game.
          Selecting the same game resumes it automatically.
        </p>
        <button autoFocus onClick={dismiss} style={{
          display: 'block', width: '100%', marginTop: 26, padding: '14px 18px',
          border: '1px solid var(--gc-overlay-border, rgba(255,255,255,.15))',
          borderRadius: 'var(--gc-overlay-radius, 16px)', cursor: 'pointer',
          color: '#fff', background: 'rgba(255,255,255,.1)', font: 'inherit',
        }}>OK</button>
      </div>
    </Overlay>
  )
}
