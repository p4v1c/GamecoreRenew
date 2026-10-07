/**
 * How a player slot is named on screen. Player 1 is the active profile, so it
 * shows that profile's name; every other slot, and player 1 on a box with no
 * profiles (an unnamed primary), stays "P<n>".
 */
import { useCallback, useEffect } from 'react'
import { api } from '../api'
import { onWsEvent } from '../hooks/useWebSocket'
import { useStore } from '../store'

/** Short form, for a status bar: "Max" or "P2". */
export const playerLabel = (player: number, playerOneName: string): string =>
  player === 1 && playerOneName ? playerOneName : `P${player}`

/** Heading form: "Max" or "Player 2". */
export const playerTitle = (player: number, playerOneName: string): string =>
  player === 1 && playerOneName ? playerOneName : `Player ${player}`

/** Sentence form, for a toast: "Max's controller" or "Controller 2". */
export const controllerTitle = (player: number | null, playerOneName: string): string => {
  if (player === 1 && playerOneName) return `${playerOneName}’s controller`
  return player ? `Controller ${player}` : 'Controller'
}

/** `(player) => label`, current with the active profile. */
export function usePlayerLabel(): (player: number) => string {
  const name = useStore((s) => s.playerOneName)
  return useCallback((player: number) => playerLabel(player, name), [name])
}

/** Keeps `playerOneName` current: read once, then on every profile change. */
export function usePlayerNames(): void {
  useEffect(() => {
    const set = (name: unknown) => useStore.getState().setPlayerOneName(typeof name === 'string' ? name : '')
    api.profiles.list()
      .then((s) => set(s.profiles.find((p) => p.id === s.active)?.name))
      .catch((e) => console.error('profiles: could not read the active profile', e))
    return onWsEvent('profiles:changed', (d) => set((d.active as { name?: unknown } | undefined)?.name))
  }, [])
}
