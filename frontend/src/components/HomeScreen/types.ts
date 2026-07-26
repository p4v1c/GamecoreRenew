import type { SystemEntry, PlaytimeEntry } from '../../api'

/**
 * What a dashboard is handed, and all it is allowed to do.
 *
 * A theme supplies one of these and nothing more: no gamepad bindings, no page
 * arithmetic, no launching. That is deliberate — every navigation bug in the
 * first theme came from a theme reimplementing this logic slightly differently
 * from the default. Behaviour lives in HomeScreen, for the default and themed
 * alike; the view only draws.
 */
export interface HomeViewProps {
  /** Every system, in order — themes that page differently still get the lot. */
  systems: SystemEntry[]
  /** Just the current page, already sliced. */
  pageItems: SystemEntry[]
  playtime: Record<string, PlaytimeEntry>
  counts: Record<string, number>
  /** Focus index *within the current page*, 0..perPage-1. */
  focusIdx: number
  page: number
  pageCount: number
  cols: number
  rows: number
  perPage: number
  totals: { systems: number; games: number; hours: number }
  /** Mouse affordances. The gamepad path never goes through these. */
  onFocus: (idx: number) => void
  onPage: (page: number) => void
  /** Focus then launch/open, by index within the current page. */
  onActivate: (idx: number) => void
}
