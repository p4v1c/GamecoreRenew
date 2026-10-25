import { useEffect } from 'react'
import { onWsEvent } from './useWebSocket'

type Loading = { game_key: string; system_id: string }

/**
 * The launch cover, relayed from the backend to the shell.
 *
 * `game:loading` comes before the spawn (backend/services/launch_ready.py), so
 * the cover is up before the emulator maps a window. It comes down on the
 * game's own signal, or when that launch fails or ends. An event about another
 * game leaves it alone: the cover belongs to the launch that raised it.
 */
export function useLaunchCover(): void {
  useEffect(() => {
    let loading: Loading | null = null
    const ours = (d: Record<string, unknown>) =>
      loading !== null && d.game_key === loading.game_key && d.system_id === loading.system_id

    const offs = [
      onWsEvent('game:loading', (d) => {
        loading = { game_key: String(d.game_key ?? ''), system_id: String(d.system_id ?? '') }
        window.gamecore?.coverShow?.({ ...loading, timeout_s: Number(d.timeout_s) || undefined })
      }),
      ...['game:ready', 'game:failed', 'game:finished'].map((event) =>
        onWsEvent(event, (d) => {
          if (!ours(d)) return
          loading = null
          window.gamecore?.coverHide?.()
        })),
    ]
    return () => offs.forEach((off) => off())
  }, [])
}
