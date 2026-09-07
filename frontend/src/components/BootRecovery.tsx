/**
 * What the box says when it cannot finish starting.
 *
 * The rule this screen exists to keep: a boot that is stuck must never be
 * resolved by showing the home anyway. The home built from a backend that
 * never answered is a dashboard with no consoles on it, and from a sofa that
 * is indistinguishable from a box that has lost its games — the player reaches
 * for the settings, finds nothing, and reinstalls.
 *
 * So the timeout does not promote anything. It ends the silence: it says which
 * step is outstanding, and offers the one action that can help from here.
 * ✕ retries, because the pad is the only input this room has.
 */
import { useEffect } from 'react'
import { onGp } from '../hooks/useGamepad'

interface Props {
  steps: Record<string, boolean>
  onRetry: () => void
}

export default function BootRecovery({ steps, onRetry }: Props) {
  useEffect(() => onGp('gp:confirm', onRetry), [onRetry])

  const waiting = Object.entries(steps).filter(([, done]) => !done).map(([name]) => name)

  return (
    <div style={styles.root}>
      <div style={styles.box}>
        <b style={styles.title}>GameCore n’a pas fini de démarrer</b>
        <p style={styles.body}>
          {waiting.length
            ? `En attente : ${waiting.join(', ')}.`
            : 'L’interface ne répond pas.'}
        </p>
        <p style={styles.hint}>
          Le service peut être encore en train de démarrer. Réessayer ne perd rien.
        </p>
        <button style={styles.button} onClick={onRetry} autoFocus>
          ✕ Réessayer
        </button>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    position: 'fixed', inset: 0, zIndex: 9500,
    background: '#09090f',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontFamily: 'system-ui, sans-serif',
  },
  box: { maxWidth: 620, padding: '0 40px', textAlign: 'center', color: '#e8e8f0' },
  title: { fontSize: 26, display: 'block', marginBottom: 18 },
  body: { fontSize: 16, opacity: 0.85, margin: '0 0 8px' },
  hint: { fontSize: 14, opacity: 0.55, margin: '0 0 28px' },
  button: {
    fontSize: 16, padding: '12px 28px', borderRadius: 10,
    border: '1px solid rgba(255,255,255,0.18)',
    background: 'rgba(255,255,255,0.08)', color: '#e8e8f0', cursor: 'pointer',
  },
}
