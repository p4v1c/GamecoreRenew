import { flushSync } from 'react-dom'
import { useStore } from '../store'
import { api } from '../api'

type Stage = 'off' | 'screensaver' | 'sleep'

/**
 * Move to a standby stage as a crossfade of the whole page, on every theme.
 *
 * Each theme's standby mounts and unmounts with the stage, so a plain store
 * write cut straight from the dashboard to the room, the room to black, and
 * back. A view transition snapshots the page before the write and fades to
 * the page after it, whatever drew either; the duration is in index.html.
 *
 * Entering `sleep`, the backend holds the screen on until the fade is over:
 * `POST /api/standby/dark` tells it, so DPMS cuts an already black frame.
 */
export function fadeToStandby(stage: Stage): void {
  const apply = () => flushSync(() => useStore.getState().setStandby(stage))
  const animate = typeof document.startViewTransition === 'function'
    && useStore.getState().standby !== stage
    && !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const faded = animate
    ? document.startViewTransition(apply).finished.catch(() => {})
    : Promise.resolve(apply())
  if (stage !== 'sleep') return
  faded.then(() => {
    // Woken during the fade: the screen must stay on.
    if (useStore.getState().standby === 'sleep') api.standby.dark().catch(() => {})
  })
}
