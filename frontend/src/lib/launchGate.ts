import { api } from '../api'
import { useStore } from '../store'
import { applySessionState } from '../hooks/useWebSocket'

export type GameLaunchDecision = 'launch' | 'resumed' | 'blocked'

/**
 * Decide what selecting a game means before any theme starts its ceremony.
 *
 * Applications deliberately do not pass through here: GameCore has always
 * allowed an app beside a suspended game. The invariant requested here is one
 * resident *game*. Every launch surface calls this function, while the backend
 * repeats the rule for clients and races that do not pass through the UI.
 */
export function gateGameLaunch(
  systemId: string,
  gameKey: string,
): GameLaunchDecision | Promise<GameLaunchDecision> {
  const held = useStore.getState().backgroundSessions.filter(s => s.kind === 'game')
  if (!held.length) return 'launch'

  const same = held.find(s => s.systemId === systemId && s.gameKey === gameKey)
  if (same) {
    return api.games.foreground(same.session).then(state => {
      applySessionState(state)
      return 'resumed'
    })
  }

  useStore.getState().setLaunchConflict(held[0])
  return 'blocked'
}
