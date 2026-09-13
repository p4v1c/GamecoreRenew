/**
 * `useStoreJobs` — the one implementation of the queue, tested on its own.
 *
 * The same reason `catalog.test.tsx` and `storeSearch.test.tsx` beside it
 * exist: the point of a module is that the second screen to want a download
 * queue cannot start a second copy, and a module that could only be exercised
 * through `StoreScreen` would be one refactor away from being inlined back
 * into it.
 *
 * `StoreScreen`'s own file tests the cursor and the markup. What is here is
 * everything neither it nor a theme may decide again — what a state means,
 * which rows can still be stopped, and what the screen is told when the box
 * refuses.
 */
import { render, act, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** The WebSocket bus, replaced by something this file can fire by hand. */
const listeners = vi.hoisted(() => new Map<string, Set<(data: unknown) => void>>())
vi.mock('../hooks/useWebSocket', async (orig) => ({
  ...await orig<Record<string, unknown>>(),
  onWsEvent: (name: string, fn: (d: unknown) => void) => {
    if (!listeners.has(name)) listeners.set(name, new Set())
    listeners.get(name)!.add(fn)
    return () => listeners.get(name)?.delete(fn)
  },
}))

import { api, type StoreJob, type StoreJobState, type StoreSearchResult } from '../api'
import {
  useStoreJobs, isLive, QUEUE_FAILED, JOB_STATE_LABELS, TERMINAL_STATES,
  type StoreJobsState,
} from './storeJobs'

const job = (id: string, state: StoreJobState, extra: Partial<StoreJob> = {}): StoreJob => ({
  id, systemId: 'nes', romsDir: 'emu/nes', title: id, filename: `${id}.nes`,
  format: 'nes', size: 1024, provider: 'demo', state, reason: '',
  queuedAt: '2026-09-13T10:00:00+00:00', startedAt: '', endedAt: '', ...extra,
})

const RESULT: StoreSearchResult = {
  id: 'r1', title: 'Zelda', filename: 'Zelda (USA).nes', format: 'nes',
  size: 1024, systemId: 'nes', provider: 'demo', source: 'demo://nes/zelda',
  region: 'USA', languages: ['en'],
}

const flush = () => act(async () => { await new Promise(r => setTimeout(r, 0)) })
const emit = (name: string, data: unknown) =>
  act(async () => {
    listeners.get(name)?.forEach(fn => fn(data))
    await new Promise(r => setTimeout(r, 0))
  })

/** Mount the hook and hand back a live read of what it returns. */
async function mount() {
  let seen!: StoreJobsState
  const Probe = () => { seen = useStoreJobs(); return null }
  render(<Probe />)
  await flush()
  return () => seen
}

beforeEach(() => {
  vi.spyOn(api.store, 'jobs').mockResolvedValue({ jobs: [], downloadReady: false })
  vi.spyOn(api.store, 'queue').mockResolvedValue(job('new', 'queued'))
  vi.spyOn(api.store, 'cancel').mockResolvedValue(job('a', 'cancelled'))
})

afterEach(() => { cleanup(); vi.restoreAllMocks(); listeners.clear() })


describe('the vocabulary a theme may not respell', () => {
  it('knows exactly five states and which three are the end', () => {
    expect(Object.keys(JOB_STATE_LABELS).sort())
      .toEqual(['cancelled', 'done', 'failed', 'queued', 'running'])
    expect(TERMINAL_STATES).toEqual(['done', 'failed', 'cancelled'])
    // `cancelled` and `failed` are two different things that happened and must
    // not read as one — they are the whole reason the labels are here rather
    // than in a view.
    expect(JOB_STATE_LABELS.cancelled).not.toBe(JOB_STATE_LABELS.failed)
  })

  it('calls a job live while it is queued or running and not after', () => {
    expect(isLive(job('a', 'queued'))).toBe(true)
    expect(isLive(job('a', 'running'))).toBe(true)
    for (const state of TERMINAL_STATES) {
      expect(isLive(job('a', state))).toBe(false)
    }
  })
})


describe('reading the queue', () => {
  it('asks once on mount and counts what is still live', async () => {
    vi.mocked(api.store.jobs).mockResolvedValue({
      jobs: [job('a', 'running'), job('b', 'queued'), job('c', 'failed')],
      downloadReady: false,
    })
    const s = await mount()
    expect(api.store.jobs).toHaveBeenCalledTimes(1)
    expect(s().jobs.map(j => j.id)).toEqual(['a', 'b', 'c'])
    expect(s().liveCount).toBe(2)
    expect(s().loading).toBe(false)
    expect(s().error).toBe('')
  })

  it('keeps the finished rows, because they are the ones read afterwards', async () => {
    // A download that failed at three in the morning is only ever read about
    // later. A queue that emptied itself on completion would never explain
    // anything.
    vi.mocked(api.store.jobs).mockResolvedValue({
      jobs: [job('a', 'done'), job('b', 'cancelled'), job('c', 'failed')],
      downloadReady: false,
    })
    const s = await mount()
    expect(s().jobs).toHaveLength(3)
    expect(s().liveCount).toBe(0)
  })

  it('tells a queue that could not be read from a queue with nothing in it', async () => {
    vi.mocked(api.store.jobs).mockRejectedValue(new Error('down'))
    const s = await mount()
    expect(s().jobs).toEqual([])
    expect(s().error).toBe(QUEUE_FAILED)
  })

  it('carries downloadReady from the backend rather than deciding it', async () => {
    // False today, and read rather than hardcoded so a screen written now is
    // already right the day bytes really land in a ROM directory.
    const s = await mount()
    expect(s().downloadReady).toBe(false)

    vi.mocked(api.store.jobs).mockResolvedValue({
      jobs: [], downloadReady: true })
    await act(async () => { await s().load() })
    expect(s().downloadReady).toBe(true)
  })

  it('keeps staging readiness separate from a playable library entry', async () => {
    vi.mocked(api.store.jobs).mockResolvedValue({
      jobs: [], downloadReady: false, materializerReady: true,
    })
    const s = await mount()
    expect(s().materializerReady).toBe(true)
    expect(s().downloadReady).toBe(false)
  })

  it('re-reads when a job moves rather than patching its own list', async () => {
    // The socket is a signal, not a source of truth: a list assembled from
    // events is wrong for as long as the socket was down, and there is no way
    // for it to notice.
    const s = await mount()
    expect(api.store.jobs).toHaveBeenCalledTimes(1)

    vi.mocked(api.store.jobs).mockResolvedValue({
      jobs: [job('a', 'failed', { reason: 'no acquisition provider is configured on this box' })],
      downloadReady: false,
    })
    await emit('store:jobs', { job: job('a', 'failed') })
    expect(api.store.jobs).toHaveBeenCalledTimes(2)
    expect(s().jobs[0].reason).toContain('no acquisition provider')
  })
})


describe('putting one in', () => {
  it('sends the result the player is looking at and shows the row at once', async () => {
    const s = await mount()
    vi.mocked(api.store.jobs).mockResolvedValue({
      jobs: [job('new', 'queued')], downloadReady: false })

    let created: StoreJob | null = null
    await act(async () => { created = await s().queue(RESULT) })

    expect(api.store.queue).toHaveBeenCalledWith(RESULT)
    expect(created!.id).toBe('new')
    // Re-read straight away rather than waiting for the socket: the player is
    // looking at the screen that made the request.
    expect(s().jobs.map(j => j.id)).toEqual(['new'])
    expect(s().actionError).toBe('')
  })

  it('keeps the box’s own sentence when the queue refuses', async () => {
    // "already in the queue", "the queue is full", "not an installed console".
    // A generic "409 Conflict" on a television is a dead end.
    vi.mocked(api.store.queue).mockRejectedValue(new Error('that is already in the queue'))
    const s = await mount()
    let created: StoreJob | null = job('x', 'queued')
    await act(async () => { created = await s().queue(RESULT) })
    expect(created).toBeNull()
    expect(s().actionError).toBe('that is already in the queue')
  })

  it('clears the last refusal when the next attempt starts', async () => {
    vi.mocked(api.store.queue).mockRejectedValueOnce(new Error('the queue is full'))
    const s = await mount()
    await act(async () => { await s().queue(RESULT) })
    expect(s().actionError).toBe('the queue is full')
    await act(async () => { await s().queue(RESULT) })
    expect(s().actionError).toBe('')
  })

})


describe('taking one out', () => {
  it('cancels a job that has not finished', async () => {
    const s = await mount()
    await act(async () => { await s().cancel(job('a', 'running')) })
    expect(api.store.cancel).toHaveBeenCalledWith('a')
  })

  it('does nothing at all to a job that is already finished', async () => {
    // ✕ lands wherever the cursor happens to be. A finished row absorbs it
    // silently rather than turning it into a 409 the player did not cause —
    // and this is decided here, so no view has to decide it again.
    const s = await mount()
    for (const state of TERMINAL_STATES) {
      await act(async () => { await s().cancel(job('a', state)) })
    }
    expect(api.store.cancel).not.toHaveBeenCalled()
    expect(s().actionError).toBe('')
  })

  it('keeps the box’s sentence when a cancel is refused', async () => {
    vi.mocked(api.store.cancel).mockRejectedValue(
      new Error('that job finished before it could be cancelled'))
    const s = await mount()
    await act(async () => { await s().cancel(job('a', 'running')) })
    expect(s().actionError).toContain('finished before it could be cancelled')
  })

  it('re-reads after a cancel, whether it worked or not', async () => {
    const s = await mount()
    expect(api.store.jobs).toHaveBeenCalledTimes(1)
    await act(async () => { await s().cancel(job('a', 'running')) })
    expect(api.store.jobs).toHaveBeenCalledTimes(2)

    vi.mocked(api.store.cancel).mockRejectedValue(new Error('nope'))
    await act(async () => { await s().cancel(job('b', 'queued')) })
    expect(api.store.jobs).toHaveBeenCalledTimes(3)
  })
})


describe('what this module deliberately cannot do', () => {
  it('offers no way to restart a finished job', async () => {
    // Asking again is queueing the result again — a new row — not
    // resurrecting the old one. There is no endpoint that restarts a job, and
    // a second way to change a state the backend owns one way of changing is
    // exactly the drift this module exists to prevent.
    const s = await mount()
    expect(Object.keys(s()).filter(k => /retry|restart|requeue|resume/i.test(k)))
      .toEqual([])
    expect(Object.keys(api.store).filter(k => /retry|restart|delete|remove/i.test(k)))
      .toEqual([])
  })
})
