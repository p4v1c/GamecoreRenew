import type { CatalogEntry } from '../../api'

/** The Store's two tabs, in the order L1/R1 walk them. */
export type StoreTab = 'consoles' | 'games'

export const STORE_TABS: StoreTab[] = ['consoles', 'games']

export const STORE_TAB_LABELS: Record<StoreTab, string> = {
  consoles: 'Consoles',
  games: 'Games',
}

/**
 * What a store screen is handed, and all it is allowed to do.
 *
 * The same seam as the dashboard and the library: which tab is open, where the
 * cursor is, which page it is on and every gamepad binding live in StoreScreen,
 * for the default and themed alike. A view only draws — so a themed store
 * cannot page differently, lose a tab, or forget that ○ goes home.
 *
 * See `HomeScreen/types.ts` and `LibraryScreen/types.ts`: this file is written
 * to the same rule, and for the same reason. Every navigation bug in the first
 * theme came from a theme reimplementing that logic slightly differently.
 */
export interface StoreViewProps {
  /** Which tab is open. */
  tab: StoreTab
  /**
   * Every tab the host cycles through with L1/R1, and their labels.
   *
   * Handed over rather than left to the view, exactly as `sortKeys` is in the
   * library: the view does not choose them. A theme that typed its own copy
   * would draw one set of tabs while the shoulder buttons walked another the
   * day a third one is added.
   */
  tabs: StoreTab[]
  tabLabels: Record<StoreTab, string>

  /** Every emulator pack in the catalogue, in the order the cursor walks. */
  consoles: CatalogEntry[]
  /** Just the current page, already sliced. */
  pageItems: CatalogEntry[]
  /** Focus index *within the current page*, 0..perPage-1. */
  focusIdx: number
  page: number
  pageCount: number
  cols: number
  rows: number
  perPage: number
  /** How many of `consoles` already have a tile on the grid. */
  installedCount: number

  loading: boolean
  loadError: boolean

  /**
   * ── Installing, removing, reconfiguring ───────────────────────────────────
   *
   * The point of the whole block below is that a theme can draw an Install
   * button without owning what pressing it means. `useCatalog` owns that — one
   * action at a time box-wide, a removal armed before it is done, the re-read
   * when `catalog:done` arrives — and a view that reimplemented any of it would
   * be the fourth copy of a sequence this repo has already had three of.
   */

  /** The pack this screen is working on right now, `''` when none. */
  workingId: string
  /**
   * Something is running on the box — this screen's action or another's.
   *
   * Draw the whole grid as held while it is true, not just the working card.
   * The backend takes one action at a time and answers 409 to a second, so a
   * view that let a player press ✕ on a second console would be offering three
   * failures.
   */
  busy: boolean
  /**
   * The id whose removal is armed: ✕ once to arm it, ✕ again to do it.
   *
   * Removing is the one irreversible thing on this screen and ✕ lands wherever
   * the cursor happens to be, so it asks twice. A view that drew no difference
   * between armed and not would make the first press look like nothing
   * happened and the second like a single-press delete.
   */
  armedId: string
  /** `gamecore-emu`'s output for the run in progress — empty between runs. */
  log: string[]
  /** What a failed run left behind. Distinct from `loadError`, which is the
   *  catalogue itself being unreadable. */
  actionError: string

  /**
   * Whether the Games tab has anything to list.
   *
   * `false` for the whole of this step, and stated in the contract rather than
   * left to the view to know: searching and downloading arrive later, and a
   * theme that drew an empty grid instead of an honest "not yet" would be
   * telling the player they own no games. When the tab gains its listing this
   * turns true and a view written now keeps working.
   */
  gamesReady: boolean

  /** Mouse affordances. The gamepad path never goes through these. */
  onTab: (tab: StoreTab) => void
  onFocus: (idx: number) => void
  onPage: (page: number) => void
  onBack: () => void
  onRetry: () => void
  /**
   * Install it, or arm its removal and then remove it — one call for both, so
   * a view never has to decide which verb a card is offering.
   *
   * ✕ is bound to this on the host's side. Wiring it to a click as well is
   * what makes the card work under a pointer; it is the same call.
   */
  onAct: (pack: CatalogEntry) => void
  /** Re-run an installed pack's configuration, leaving the install alone. △ on
   *  the host's side; a no-op on a pack that is not installed. */
  onReconfigure: (pack: CatalogEntry) => void
}
