import { useEffect } from 'react'
import { api } from '../api'

/**
 * A mouse move or a key press ends standby. The backend never sees either:
 * it only hears controllers (gamepad_monitor), whose first press the input
 * bus swallows as the wake itself (useGamepad).
 */
export function useLocalWake(stage: 'off' | 'screensaver' | 'sleep'): void {
  useEffect(() => {
    if (stage === 'off') return
    const wake = () => { api.standby.exit().catch(() => {}) }
    window.addEventListener('pointermove', wake)
    window.addEventListener('keydown', wake)
    return () => {
      window.removeEventListener('pointermove', wake)
      window.removeEventListener('keydown', wake)
    }
  }, [stage])
}
