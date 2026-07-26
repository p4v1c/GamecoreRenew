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
   */
  Cover: ComponentType<{ filename: string; systemId: string; color: string }>
  Meta: ComponentType<{ systemId: string; filename: string; extChip: ReactNode; color: string }>
}
