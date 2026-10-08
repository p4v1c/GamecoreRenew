/**
 * How a player slot is named on screen. A pad linked to a profile (its page →
 * Controllers) shows that profile's name, whichever profile is active; any
 * other pad, and every pad on a box without profiles, stays "P<n>".
 */
import { useCallback, useEffect } from 'react'
import { api } from '../api'
import type { Profile, RosterPad } from '../api'
import { onWsEvent } from '../hooks/useWebSocket'
import { useStore } from '../store'

/** Player slot → the name of the profile its pad is linked to. */
export type PadOwners = Record<number, string>

/** Which profile each connected pad is linked to, by `RosterPad.id`. */
export const padOwners = (roster: readonly RosterPad[], profiles: readonly Profile[]): PadOwners => {
  const owners: PadOwners = {}
  for (const pad of roster) {
    if (!pad.player) continue
    const owner = profiles.find((p) => p.name && p.controllers?.some((c) => c.id === pad.id))
    if (owner) owners[pad.player] = owner.name
  }
  return owners
}

/** Short form, for a status bar: "Max" or "P2". */
export const playerLabel = (player: number, owners: PadOwners): string => owners[player] || `P${player}`

/** Heading form: "Max" or "Player 2". */
export const playerTitle = (player: number, owners: PadOwners): string => owners[player] || `Player ${player}`

/** Sentence form, for a toast: "Max's controller" or "Controller 2". */
export const controllerTitle = (player: number | null, owners: PadOwners): string => {
  if (player && owners[player]) return `${owners[player]}’s controller`
  return player ? `Controller ${player}` : 'Controller'
}

/** `(player) => label`, current with the pads and their profiles. */
export function usePlayerLabel(): (player: number) => string {
  const owners = useStore((s) => s.padOwners)
  return useCallback((player: number) => playerLabel(player, owners), [owners])
}

/** Reads the profiles and the roster; the result writes them to the store. */
async function readPlayers(): Promise<() => void> {
  const [state, roster] = await Promise.all([
    api.profiles.list().catch((e) => { console.error('profiles: could not read the profiles', e); return null }),
    api.controllers.pads().then((r) => r.pads ?? []).catch(() => null),
  ])
  return () => {
    if (!state) return
    const store = useStore.getState()
    const p = state.profiles.find((x) => x.id === state.active)
    store.setActiveProfile(p?.name ?? '', p && !p.primary ? p.id : '',
      { color: p?.color ?? '', avatar: p?.avatar ?? null })
    // ponytail: a failed roster read keeps the last labels; the next pad event retries.
    if (roster) store.setPads(roster, padOwners(roster, state.profiles))
  }
}

let latest: Promise<void> | null = null

/**
 * Re-reads the profiles and the roster into the store; resolves once the
 * store holds the newest read. Events come in bursts (a departure, then its
 * slot compaction), so an older read that lands late is dropped.
 */
export function refreshPlayers(): Promise<void> {
  const mine: Promise<void> = readPlayers().then((write) => {
    if (latest === mine) write()
    else return latest!
  })
  latest = mine
  return mine
}

/** Keeps the active profile and the pad labels current: on mount, on every
 *  profile change, and whenever a pad arrives, leaves or changes slot. */
export function usePlayerNames(): void {
  useEffect(() => {
    refreshPlayers()
    const offs = ['profiles:changed', 'gp:connected', 'gp:disconnected', 'gp:controllers']
      .map((event) => onWsEvent(event, () => { refreshPlayers() }))
    return () => offs.forEach((off) => off())
  }, [])
}

/** `base` for the primary profile, `base:<id>` for another: a theme's own
 *  per-profile storage, with the primary keeping what it had before profiles. */
export const profileStorageKey = (base: string): string => {
  const key = useStore.getState().profileKey
  return key ? `${base}:${key}` : base
}

/** `fn()` after the active profile changes. Returns the unsubscribe. */
export const onProfileChange = (fn: () => void): (() => void) =>
  useStore.subscribe((s, prev) => { if (s.profileKey !== prev.profileKey) fn() })
