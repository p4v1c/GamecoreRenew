/**
 * What the standby TV shows next, and for how long. Pure: the CRT standby
 * (components/CrtStandby) owns the timers and the video elements.
 */
import type { StandbyItem, StandbyPlaylist } from '../api/standby'

/** A clip plays this long at most: enough to recognise the game. */
export const CLIP_MAX_S = 25
/** One screenshot on screen, Ken Burns included. */
export const STILL_S = 9
/** The snow between two channels. */
export const STATIC_MS = 450

export type ReelMode = 'video' | 'still' | 'none'

/** Videos when there are any, screenshots otherwise, else the "no signal" TV. */
export function reelMode(list: StandbyPlaylist | null): ReelMode {
  if (list?.videos?.length) return 'video'
  if (list?.stills?.length) return 'still'
  return 'none'
}

export function reelItems(list: StandbyPlaylist | null, mode: ReelMode): StandbyItem[] {
  if (!list || mode === 'none') return []
  return mode === 'video' ? list.videos : list.stills
}

/** How long to play a clip of `duration` seconds (NaN or Infinity: unknown). */
export function clipSeconds(duration: number): number {
  if (!Number.isFinite(duration) || duration <= 0) return CLIP_MAX_S
  return Math.min(duration, CLIP_MAX_S)
}

/** The slot after `i` in a list of `n`, wrapping. A list of one replays itself. */
export function nextIndex(i: number, n: number): number {
  return n > 0 ? (i + 1) % n : 0
}

const DAY_MS = 86_400_000

/**
 * "played 3 days ago", from the playtime table's local timestamp, or null when
 * the game was never played. Whole calendar days, so last night is "yesterday".
 */
export function playedAgo(lastPlayed: string | null | undefined, now: Date): string | null {
  if (!lastPlayed) return null
  const when = new Date(lastPlayed)
  if (Number.isNaN(when.getTime())) return null
  const day = (d: Date) => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())
  const days = Math.max(0, Math.round((day(now) - day(when)) / DAY_MS))
  if (days === 0) return 'played today'
  if (days === 1) return 'played yesterday'
  if (days < 14) return `played ${days} days ago`
  if (days < 60) return `played ${Math.round(days / 7)} weeks ago`
  if (days < 730) return `played ${Math.round(days / 30)} months ago`
  return `played ${Math.round(days / 365)} years ago`
}

/** The caption's second line: "Super Nintendo, played 3 days ago". */
export function captionMeta(item: StandbyItem, now: Date): string {
  const ago = playedAgo(item.last_played, now)
  return ago ? `${item.system_name}, ${ago}` : item.system_name
}
