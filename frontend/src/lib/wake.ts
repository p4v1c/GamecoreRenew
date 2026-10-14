/**
 * The interface's half of a wake from sleep.
 *
 * The backend counts wakes (`resumes`) and announces each one over the socket
 * (`power:resumed`). A socket can drop across a sleep, so every reconnect also
 * reads the count: a number that grew while nobody was listening is a wake
 * this page missed. A backend restart resets it, which is not a wake.
 *
 * The backend counts a wake only once the TV shows a picture again
 * (backend/services/display_ready.py), so the splash replayed here plays whole.
 */
import { api } from '../api'
import { useStore } from '../store'

let lastResumes: number | null = null

/** A `power:resumed` event. Replayed events (same count) are ignored. */
export function onResumed(resumes: unknown): void {
  const n = typeof resumes === 'number' ? resumes : null
  if (n !== null && lastResumes !== null && n <= lastResumes) return
  if (n !== null) lastResumes = n
  useStore.getState().wake()
}

/** `power:sleeping`: black over everything until the wake is announced. */
export function onSleeping(): void {
  useStore.getState().setAsleep(true)
}

/** On every socket open. A failed request changes nothing. */
export async function syncWake(): Promise<void> {
  try {
    const { resumes, sleeping, resting } = await api.power.state()
    if (lastResumes !== null && resumes > lastResumes) useStore.getState().wake()
    // A black layer the backend no longer stands behind (a page reloaded, an
    // announcement lost) would hide the box for good.
    else if (!sleeping && !resting && useStore.getState().asleep) useStore.getState().setAsleep(false)
    lastResumes = resumes
  } catch { /* the socket will tell us */ }
}

/** Tests only: forget what this page has seen. */
export function resetWakeForTests(): void {
  lastResumes = null
}
