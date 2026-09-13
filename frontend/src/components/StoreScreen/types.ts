import type { CatalogEntry, StoreJob, StoreSearchResult } from '../../api'

/** The Store's two tabs, in the order L1/R1 walk them. */
export type StoreTab = 'consoles' | 'games'

export const STORE_TABS: StoreTab[] = ['consoles', 'games']

export const STORE_TAB_LABELS: Record<StoreTab, string> = {
  consoles: 'Consoles',
  games: 'Games',
}

/**
 * Which step of the Games tab the player is on.
 *
 * Two, and the order is not a menu preference: a game is searched for *inside*
 * a console, because the ingestion class of a download is a property of the
 * pair (system, incoming format) and the directory it lands in is a property
 * of the system. A result found without a console attached could be neither
 * placed nor classified — `docs/architecture/14-store-ingestion-matrix.md` §0,
 * §1.3.
 *
 * The third is not a step of that sequence but a place the player goes: the
 * queue of what has already been asked for. It is reachable from the first
 * (△) and it is where asking for a result lands them, so that a press which
 * created a row shows them the row.
 */
export type StoreGamesPhase = 'systems' | 'results' | 'queue'

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
  /** Just the current page of them, already sliced — the Consoles tab. */
  pageItems: CatalogEntry[]
  /**
   * ── The cursor, wherever it happens to be ─────────────────────────────────
   *
   * One cursor, describing whichever list is under it: the Consoles tab's
   * grid, the Games tab's console list, or its results. It resets when the
   * tab changes and when the Games tab steps between its two phases, because
   * a highlight at card 9 of a list with three rows is a highlight nobody can
   * see.
   *
   * `cols` / `rows` / `perPage` describe **that same list** and change with
   * it — a results page is a column of rows where a console page is a grid.
   * Read them rather than hard-coding 4 × 3, or a themed store draws twelve
   * slots for eight results and pages them wrong.
   */
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
   * True since searching arrived. It stays in the contract because the
   * promise it was written with still holds from the other side: a view built
   * while it was `false` drew an honest "not yet" and still works, and one
   * written now must not assume the tab can never be empty-handed again.
   */
  gamesReady: boolean

  /**
   * ── The Games tab ─────────────────────────────────────────────────────────
   *
   * Two steps: pick a console, then search inside it. The block below is what
   * a view draws them with, and the same rule applies as to the Consoles tab
   * above — which console is chosen, what was searched for, and what came back
   * are the host's, through `useStoreSearch` (`frontend/src/lib/storeSearch.ts`).
   * A view that ran its own search would be the second implementation this
   * repository already learned not to have.
   *
   * **Why the console comes first**, since a theme will be tempted to offer a
   * search box on the tab's first screen: the ingestion class of a download is
   * a property of the pair (system, incoming format) — the same `.zip` is the
   * ROM on `mame` and packaging on `snes9x` — and the directory it has to land
   * in belongs to the system. A result found without a console attached can be
   * neither placed nor classified, and no indexer labels its results by
   * console reliably enough to attach one afterwards. See
   * `docs/architecture/14-store-ingestion-matrix.md` §0 and §1.3.
   */
  gamesPhase: StoreGamesPhase
  /**
   * The consoles that can be searched: the installed ones, A–Z.
   *
   * Only the installed ones, and that is not a convenience either — a game for
   * a console that is not on the box lands in a directory nothing scans, for a
   * tile that is not on the grid. The list is `consoles` filtered, not a
   * second read of the catalogue.
   */
  gamesSystems: CatalogEntry[]
  /** Just the current page of them, already sliced — the `systems` phase. */
  gamesSystemsPage: CatalogEntry[]
  /** The console being searched; `null` in the `systems` phase. */
  gamesSystem: CatalogEntry | null
  /** What was searched for; `''` before the first search. */
  gamesQuery: string
  /** Everything that came back, in the order the cursor walks it. */
  gamesResults: StoreSearchResult[]
  /** Just the current page of them, already sliced — the `results` phase. */
  gamesResultsPage: StoreSearchResult[]
  /** A search is in flight. */
  gamesLoading: boolean
  /** The search failed. Empty when nothing is wrong — **no results is not an
   *  error** and a view that drew it as one would be blaming the box for a
   *  query that simply matched nothing. */
  gamesError: string
  /** True once a search has answered, so "nothing matched" can be told apart
   *  from "nothing has been searched for yet". */
  gamesAnswered: boolean
  /**
   * Whether the rows describe real sources.
   *
   * `false` while the only provider is the demo one, which invents them.
   * **Draw it.** A tab that showed invented rows exactly as it will show an
   * indexer's would be inviting a player to press ✕ on a game that does not
   * exist, and that is a worse lie than the empty state this tab replaced.
   */
  gamesLive: boolean
  /** What to call the provider that answered. */
  gamesProvider: string
  /**
   * Where a download for the chosen console would land — `emu/<dir>`,
   * relative to the data root. Known only after a search has answered.
   */
  gamesRomsDir: string
  /** The result the player has asked about; `null` when none. */
  gamesAsked: StoreSearchResult | null
  /**
   * Whether asking for a result can actually bring it onto the box.
   *
   * **Still `false`, and it is not the same flag as "materialized".** This
   * promises *bytes imported into a ROM directory*. The worker can now fetch
   * into private staging, but that is not a playable tile; the distinct
   * `gamesMaterializerReady` flag says only that earlier promise.
   *
   * Read from the backend rather than decided here, so a view written now is
   * already right on the day it changes.
   */
  gamesDownloadReady: boolean
  /** Bytes may reach per-job staging; this never promises a library tile. */
  gamesMaterializerReady: boolean

  /**
   * ── The queue ─────────────────────────────────────────────────────────────
   *
   * What the player has already asked for, whatever became of it. A row and
   * not a variable: it is written to the box's database, it survives the
   * screen, the tab and a reboot, and a job the box was killed in the middle
   * of comes back saying so rather than saying it is still running.
   *
   * The same rule as everything above — the list, the states and the two
   * actions are the host's, through `useStoreJobs`
   * (`frontend/src/lib/storeJobs.ts`). A view draws them. What a view must not
   * do is invent a sixth state, or decide that a finished row can be cancelled.
   */

  /** Every job, newest first, in the order the cursor walks it. */
  gamesJobs: StoreJob[]
  /** Just the current page of them, already sliced — the `queue` phase. */
  gamesJobsPage: StoreJob[]
  /** How many are still queued or running. What a badge counts, and what makes
   *  "△ the queue" worth pressing. */
  gamesJobsLive: number
  /** The queue could not be read. Empty when nothing is wrong — **an empty
   *  queue is not an error** and a view that drew it as one would be blaming
   *  the box for a player who has not asked for anything yet. */
  gamesJobsError: string
  /** A queue request is in flight. */
  gamesQueueing: boolean
  /**
   * Why the last queue or cancel was refused, in the backend's own words:
   * already in the queue, the queue is full, that console is not installed.
   * Empty when nothing was refused. Draw it — it is the actionable half.
   */
  gamesQueueError: string

  /** Pick the console to search inside — the `systems` phase's action. */
  onGamesSystem: (system: CatalogEntry) => void
  /** Open the on-screen keyboard. The keyboard itself is the host's: a themed
   *  store cannot ship without a way to type, and it is what registers as a
   *  modal so the global shortcuts stand down over it. */
  onGamesSearch: () => void
  /** Ask about one result. Opens the panel; queues nothing. */
  onGamesAsk: (result: StoreSearchResult) => void
  /**
   * Queue the result the player is looking at — the asked panel's one action,
   * and ✕ on the host's side while that panel is up.
   *
   * It writes a row and steps to the queue, so that the press which created it
   * shows it. It does **not** download anything: see `gamesDownloadReady`.
   */
  onGamesQueue: (result: StoreSearchResult) => void
  /** Open the queue. △ on the host's side, from the console list. */
  onGamesQueueOpen: () => void
  /** Stop one job, whether it has started or not. A no-op on a finished row —
   *  the host decides that, not the view. */
  onGamesCancelJob: (job: StoreJob) => void
  /** Put an asked result back down, leave the queue, or step back to the
   *  console list — whichever the player is on. */
  onGamesBack: () => void

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
