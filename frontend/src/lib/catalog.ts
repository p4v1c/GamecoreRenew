/**
 * The catalogue, and the single implementation of doing anything to it.
 *
 * `GET /api/catalog` answers with every pack the box could run — thirty-one
 * emulators and four applications — and three routes act on one: install,
 * remove, reconfigure. Two screens drive those routes now, the Store's Consoles
 * tab for the emulators and Settings → Applications for the apps, and this file
 * is why that is two screens rather than two implementations.
 *
 * It had been three. Before this module the same sequence — read the list, post
 * the verb, hold the screen until `catalog:done`, re-read — was written out in
 * `modals/settings/CatalogPage.tsx`, in `settings/catalog.js` (the rail page
 * that actually ships, on the default surface and on both themes), and a third
 * read-only half of it in `StoreScreen`. They had already drifted:
 *
 *  · **Removing was one press in the rail and two in the modal.** The two-press
 *    arm-then-confirm was written for exactly this — ✕ lands on whatever the
 *    cursor happens to be over — and only one of the two copies got it.
 *  · **Only the rail asked `GET /catalog/busy`.** The backend runs one action
 *    at a time and answers 409 to a second, so a screen that never asks starts
 *    an install that cannot run and shows it as working until it gives up.
 *  · **Applications were grouped by `kind` in one copy and by `family` in the
 *    other.** No app pack declares a family, so the rail filed Steam and
 *    YouTube under "Other" while the modal filed them under "Applications".
 *
 * Every one of those is a decision, and a decision belongs in one place. What
 * is deliberately NOT here is the ordering: which pack follows which is what a
 * cursor walks, so it stays with the screen that owns the cursor — see the
 * comment over `load` in `StoreScreen/index.tsx`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type CatalogEntry } from '../api'
import { onWsEvent } from '../hooks/useWebSocket'
import { playSound } from './sounds'

/** A pack is a console or an application, and the two have separate screens. */
export type CatalogKind = CatalogEntry['kind']

/** What `catalog:done` carries. */
export interface CatalogDone {
  action?: string
  id?: string
  success?: boolean
}

export interface UseCatalogOptions {
  /** Which half of the catalogue this screen is about. */
  kind: CatalogKind
  /**
   * Fired the moment a run finishes, before the re-read that follows it.
   *
   * The seam a screen needs to hold its cursor still across a list that is
   * about to change underneath it: by the time the new rows arrive, whatever
   * the cursor was pointing at is at a different index. Called for a failed run
   * too — see the re-read below for why a failure also changes the list.
   */
  onDone?: (done: CatalogDone) => void
}

export interface CatalogSection {
  /** The packs of this kind. `null` until the first answer, never on an error. */
  rows: CatalogEntry[] | null
  /** Every pack whatever its kind — for a count that spans both screens. */
  all: CatalogEntry[] | null
  loading: boolean
  /** The catalogue could not be read. Distinct from an action that failed. */
  loadFailed: boolean
  /** Set when a run reports an error; cleared by the next one that starts. */
  actionError: string
  /** The pack THIS screen started, `''` when none. */
  workingId: string
  /**
   * Something is running on the box — this screen's action or another's.
   *
   * The whole list is held while it is true rather than just the row: the
   * backend takes one action at a time and answers 409 to a second, so letting
   * a player queue four installs means watching three of them fail.
   */
  busy: boolean
  /** The id whose removal is armed: ✕ once to arm it, ✕ again to do it. */
  armedId: string
  /** `gamecore-emu`'s output for the run in progress. */
  log: string[]
  load: () => Promise<void>
  /** Install it, or arm its removal and then remove it. */
  act: (pack: CatalogEntry) => Promise<void>
  /** Re-run an installed pack's configuration, leaving the install alone. */
  reconfigure: (pack: CatalogEntry) => Promise<void>
  /** Stepping away is how a player says no to an armed removal. */
  disarm: () => void
}

/**
 * What a failed run leaves on screen.
 *
 * It says nothing about where to read more: one surface prints the log under
 * the list and the other has no room for it, and a sentence pointing at a pane
 * that is not there is worse than a short one.
 */
export const CATALOG_FAILED = 'That did not finish.'

/** How many lines of `gamecore-emu` output are worth keeping on screen. */
const LOG_LINES = 200

export function useCatalog({ kind, onDone }: UseCatalogOptions): CatalogSection {
  const [all, setAll] = useState<CatalogEntry[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadFailed, setLoadFailed] = useState(false)
  const [actionError, setActionError] = useState('')
  const [workingId, setWorkingId] = useState('')
  // Something started from a screen that is not this one. There is no
  // `catalog:start` event to learn it from, so it comes from asking once on
  // mount and from output arriving with nothing of ours running.
  const [elsewhere, setElsewhere] = useState(false)
  const [armedId, setArmedId] = useState('')
  const [log, setLog] = useState<string[]>([])

  const rows = useMemo(
    () => (all === null ? null : all.filter(r => r.kind === kind)),
    [all, kind],
  )

  const busy = !!workingId || elsewhere

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setAll(await api.catalog.list())
      setLoadFailed(false)
    } catch {
      // The list is left as it was rather than emptied: a screen that drops
      // every row because one poll failed reads as a box with nothing on it.
      setLoadFailed(true)
    } finally {
      setLoading(false)
    }
  }, [])

  // Read live by the handlers below, which are registered once and would
  // otherwise decide from the render that registered them.
  const busyRef = useRef(busy)
  const armedRef = useRef(armedId)
  const workingRef = useRef(workingId)
  const onDoneRef = useRef(onDone)
  busyRef.current = busy
  armedRef.current = armedId
  workingRef.current = workingId
  onDoneRef.current = onDone

  useEffect(() => {
    void load()
    // One action at a time, box-wide. Asking is the difference between holding
    // the list while another screen works and offering a button that 409s.
    api.catalog.busy().then(r => setElsewhere(!!r.busy)).catch(() => {})
  }, [load])

  useEffect(() => {
    const offs = [
      onWsEvent('catalog:log', d => {
        setLog(l => [...l.slice(-LOG_LINES), String((d as { line?: unknown })?.line ?? '')])
        // Output with nothing of ours running is the other screen's install:
        // the settings modal opens over the Store and leaves it mounted, so
        // both are listening and only one of them started anything.
        if (!workingRef.current) setElsewhere(true)
      }),
      onWsEvent('catalog:done', d => {
        const done = (d ?? {}) as CatalogDone
        setWorkingId('')
        setElsewhere(false)
        setActionError(done.success === false ? CATALOG_FAILED : '')
        onDoneRef.current?.(done)
        // Re-read on a failure too, and that is not belt-and-braces: the CLI is
        // killed at `_CLI_TIMEOUT` and reports `success: false` after however
        // much of the work it had already done (backend/routers/catalog.py,
        // `_run_cli`), and `installed` is read from the systems.json it writes.
        // A screen that skipped the re-read would keep saying "not installed"
        // about a pack that is now half on the box.
        void load()
      }),
    ]
    return () => offs.forEach(off => off())
  }, [load])

  /** Start a run and hand the screen over to `catalog:done`. */
  const start = useCallback(async (verb: 'install' | 'remove' | 'reconfigure', id: string) => {
    setWorkingId(id)
    setLog([])
    setActionError('')
    playSound('confirm')
    try {
      await api.catalog[verb](id)
    } catch (e) {
      // Nothing started, so nothing is coming back on the socket to release it.
      setWorkingId('')
      setActionError(String(e))
    }
  }, [])

  const act = useCallback(async (pack: CatalogEntry) => {
    if (busyRef.current) return
    // Installing is additive and undone from the same screen. Removing is not,
    // and ✕ lands wherever the cursor happens to be, so it asks twice.
    if (pack.installed && armedRef.current !== pack.id) {
      setArmedId(pack.id)
      playSound('move')
      return
    }
    setArmedId('')
    await start(pack.installed ? 'remove' : 'install', pack.id)
  }, [start])

  const reconfigure = useCallback(async (pack: CatalogEntry) => {
    // Nothing to reconfigure about a pack that is not on the box, and the
    // route would fail on its own terms rather than say so.
    if (busyRef.current || !pack.installed) return
    setArmedId('')
    await start('reconfigure', pack.id)
  }, [start])

  const disarm = useCallback(() => setArmedId(''), [])

  return {
    rows, all, loading, loadFailed, actionError,
    workingId, busy, armedId, log,
    load, act, reconfigure, disarm,
  }
}
