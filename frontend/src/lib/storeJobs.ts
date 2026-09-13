/**
 * The download queue, and the single implementation of it.
 *
 * Beside `storeSearch.ts`, which owns the question, this owns the answer's
 * consequence: the player pressed ✕ on a result, and that is now a row in the
 * box's database rather than a variable in a screen. Reading that list,
 * putting one in, taking one out and hearing about it when it moves are the
 * whole of this file, and the reason it is a file is the one `catalog.ts`
 * states beside it — the same sequence had been written out three times there
 * before it was a module, and the three copies had already drifted.
 *
 * ── What the queue is honest about ──────────────────────────────────────────
 * Materialization downloads into per-job staging. `materializerReady` carries
 * that promise, while `downloadReady` remains false because it means imported
 * into the playable library. Running rows carry persisted byte progress, and
 * a complete transfer fails with the backend's explicit not-imported reason.
 *
 * That is why the queue is worth having anyway. It is the difference between
 * "the box forgot" and "the box tried and here is what happened", and the
 * second one is the only one a player can act on.
 *
 * ── Why the list is re-read rather than patched ─────────────────────────────
 * `store:jobs` fires on every transition and carries the row that changed.
 * This hook uses it as a *signal* and asks the backend for the list again,
 * which `useCatalog` does with `catalog:done` for the same reason: a list
 * assembled from events is a second source of truth, and it is wrong for as
 * long as the socket was down. The box is on the other end of loopback and a
 * queue is twenty rows.
 *
 * ── What is deliberately not here ───────────────────────────────────────────
 * Retrying. A finished job is a record of what happened, and asking again is
 * queueing the result again — a new row — not resurrecting the old one. There
 * is no endpoint that restarts a job and there should not be: it would be a
 * second way to change a state the backend owns exactly one way of changing.
 */
import { useCallback, useEffect, useState } from 'react'
import { api, type StoreJob, type StoreJobState, type StoreSearchResult } from '../api'
import { onWsEvent } from '../hooks/useWebSocket'
import { playSound } from './sounds'

/** What a queue that could not be read leaves on screen. */
export const QUEUE_FAILED = 'The queue could not be read.'

/** What a queue request that failed for no stated reason leaves on screen. */
export const QUEUE_REFUSED = 'That could not be queued.'

/** A job nothing will move again. The backend's own `TERMINAL`, and the one
 *  thing a view may not decide differently: it is what makes ✕ a no-op on a
 *  finished row rather than a request that 409s. */
export const TERMINAL_STATES: StoreJobState[] = ['done', 'failed', 'cancelled']

export function isLive(job: StoreJob): boolean {
  return !TERMINAL_STATES.includes(job.state)
}

/**
 * What a state is called on a television, at two metres.
 *
 * Here rather than in a view because the five words are the vocabulary of the
 * screen and a theme that spelled its own would be a theme where `cancelled`
 * and `failed` read the same. A theme is free to draw them however it likes;
 * what it must not do is invent a sixth.
 */
export const JOB_STATE_LABELS: Record<StoreJobState, string> = {
  queued: 'WAITING',
  running: 'WORKING…',
  done: 'DONE',
  failed: 'FAILED',
  cancelled: 'CANCELLED',
}

export interface StoreJobsState {
  /** Every job, newest first. `[]` before the first answer and after a
   *  failure — see `error`, which is how the two are told apart. */
  jobs: StoreJob[]
  /** How many are still queued or running. What a badge counts. */
  liveCount: number
  /** The first read has not answered yet. */
  loading: boolean
  /** The list could not be read. Distinct from an empty queue. */
  error: string
  /**
   * Whether a finished job means bytes in a ROM directory.
   *
   * `false` for the whole of this step and read from the backend rather than
   * hardcoded here, so that the day it turns true a screen written now is
   * already right.
   */
  downloadReady: boolean
  /** Bytes can be downloaded into staging; this does not mean playable. */
  materializerReady: boolean
  /** A queue request is in flight. */
  queueing: boolean
  /**
   * Why the last queue or cancel was refused — the backend's own sentence,
   * which is the actionable half: already in the queue, the queue is full,
   * that console is not installed. Cleared by the next attempt.
   */
  actionError: string

  load: () => Promise<void>
  /**
   * Ask the box for this result. Answers the row it created, or `null` when it
   * was refused — which is what the caller needs to decide whether to show the
   * player a queue that gained a row, and is why nothing here also parks the
   * job in state nobody reads.
   */
  queue: (result: StoreSearchResult) => Promise<StoreJob | null>
  /** Stop one, whether it has started or not. A no-op on a finished job:
   *  ✕ lands wherever the cursor is, and the backend would answer 409. */
  cancel: (job: StoreJob) => Promise<void>
}

export function useStoreJobs(): StoreJobsState {
  const [jobs, setJobs] = useState<StoreJob[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [downloadReady, setDownloadReady] = useState(false)
  const [materializerReady, setMaterializerReady] = useState(false)
  const [queueing, setQueueing] = useState(false)
  const [actionError, setActionError] = useState('')

  const load = useCallback(async () => {
    try {
      const answer = await api.store.jobs()
      setJobs(answer?.jobs ?? [])
      // Coerced rather than trusted: this lands in the view props typed as a
      // boolean, and an endpoint answering a shape nobody expected must not
      // put `undefined` where a theme is about to decide what to promise.
      setDownloadReady(!!answer?.downloadReady)
      setMaterializerReady(!!answer?.materializerReady)
      setError('')
    } catch {
      // The rows are dropped rather than kept, and that is the honest answer
      // for a list whose whole value is being current: a queue drawn from an
      // answer that is minutes old would show a download as running long
      // after it stopped. `error` is what the screen draws instead.
      setJobs([])
      setError(QUEUE_FAILED)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    // Every transition, from any screen and from the worker. Used as a signal
    // and not as the row itself — see the note at the top of this file.
    const off = onWsEvent('store:jobs', () => { void load() })
    return () => off()
  }, [load])

  const queue = useCallback(async (result: StoreSearchResult) => {
    setQueueing(true)
    setActionError('')
    playSound('confirm')
    try {
      const job = await api.store.queue(result)
      // Straight away rather than waiting for the socket: the player is
      // looking at the screen that made the request, and a queue that takes a
      // round trip to show the row they just added reads as a press that did
      // nothing.
      await load()
      return job
    } catch (e) {
      // The backend's own sentence, which is the only actionable half of a
      // refusal — `api.store.queue` uses the POST that keeps FastAPI's
      // `detail`. A generic "409 Conflict" on a television is a dead end.
      setActionError(String((e as Error)?.message || QUEUE_REFUSED))
      return null
    } finally {
      setQueueing(false)
    }
  }, [load])

  const cancel = useCallback(async (job: StoreJob) => {
    // Nothing to stop, and the backend would answer 409. ✕ lands wherever the
    // cursor happens to be, so a finished row absorbs it silently rather than
    // turning it into an error the player did not cause.
    if (!isLive(job)) return
    setActionError('')
    playSound('confirm')
    try {
      await api.store.cancel(job.id)
    } catch (e) {
      setActionError(String((e as Error)?.message || QUEUE_REFUSED))
    }
    await load()
  }, [load])

  const liveCount = jobs.filter(isLive).length

  return {
    jobs, liveCount, loading, error, downloadReady, materializerReady,
    queueing, actionError,
    load, queue, cancel,
  }
}
