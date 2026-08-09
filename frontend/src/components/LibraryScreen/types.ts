import type { ComponentType, ReactNode } from 'react'
import type { GameEntry, PlaytimeEntry, SystemEntry } from '../../api'

export type SortKey = 'name' | 'playtime' | 'lastPlayed'

export const SORT_KEYS: SortKey[] = ['name', 'playtime', 'lastPlayed']

export const SORT_LABELS: Record<SortKey, string> = {
  name: 'A–Z',
  lastPlayed: 'Recent',
  playtime: 'Played',
}

/**
 * What a library screen is handed, and all it is allowed to do.
 *
 * Same seam as the dashboard: selection, sorting, searching, launching and the
 * gamepad bindings live in LibraryScreen, for the default and themed alike. A
 * view only draws — so a themed library cannot scroll differently, launch
 * differently, or forget that ○ goes home.
 */
export interface LibraryViewProps {
  systemId: string
  system: SystemEntry | null
  /** Sorted and filtered — what to render, in order. */
  games: GameEntry[]
  /** How many the system has in total, before the search filter. */
  totalCount: number
  playtime: Record<string, PlaytimeEntry>
  selectedIdx: number
  /**
   * The game the detail panel should show. Debounced behind `selectedIdx`: on a
   * fast scroll it lags 150ms, which is what stops a cover+metadata request per
   * step. Drive the list from `selectedIdx` and the panel from this.
   */
  detailGame: GameEntry | null
  sort: SortKey
  /**
   * Every sort the host cycles through with L1/R1, and their labels.
   *
   * Handed over rather than left to the view because the view does not choose
   * them: L1/R1 walk this list in LibraryScreen, so a theme that typed its own
   * copy would draw one set of options while the buttons cycled another the
   * day a fourth sort is added. The default view imported them directly, which
   * a theme cannot do.
   */
  sortKeys: SortKey[]
  sortLabels: Record<SortKey, string>
  search: string
  loading: boolean
  loadError: boolean
  launching: boolean
  /** The system's accent colour, resolved for you. */
  color: string

  onSelect: (idx: number) => void
  onSearch: (query: string) => void
  onSort: (key: SortKey) => void
  onLaunch: () => void
  onBack: () => void
  onRetry: () => void

  /**
   * Cover art and metadata, ready-made: both do their own fetching, caching and
   * fallbacks. Rebuilding them in a theme means reimplementing the 404 path.
   *
   * `Cover` takes an optional `type`: `"box-3d"`, `"clear-logo"`,
   * `"screenshot-gameplay"`, `"mix-rbv2"`… Left out, it draws the jacket from
   * /api/covers exactly as it always has, so a view written before this
   * existed behaves identically. Ask `sdk.api.media.list()` what a given game
   * actually has — it varies by game, and a type that is missing falls back to
   * the jacket rather than to a hole.
   */
  Cover: ComponentType<{ filename: string; systemId: string; color: string; type?: string }>
  Meta: ComponentType<{ systemId: string; filename: string; extChip: ReactNode; color: string }>
}
