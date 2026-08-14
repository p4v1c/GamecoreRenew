/**
 * Finding out what the box is doing, rather than assuming it is awake.
 *
 * Not reported — found because the input guard made it matter. The front end
 * learned the standby stage from three websocket events and from nothing else,
 * so it only ever knew what happened while it was listening. Two ways that goes
 * wrong, and the second is the bad one:
 *
 *   · the page reloads while the box is asleep. Chromium restarting on the box
 *     is enough. The store comes up 'off', the overlay is gone, and the first
 *     press navigates a menu on a panel the backend has switched off — the
 *     exact complaint, one press wide, until evdev wakes it.
 *
 *   · the websocket drops while the box is awake, and the box then falls
 *     asleep. `standby:sleep` is sent to nobody. The store stays 'off' for as
 *     long as the socket is down: no overlay, no guard, a live cursor over a
 *     dark television, and nothing to end it.
 *
 * One mechanism covers both, because both are the same question: ask the box
 * every time the socket comes up, which is the first connection and every
 * reconnection after it. The state is already on `GET /api/standby` — the
 * settings page has been reading it all along.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useStore } from '../store'
import { api } from '../api'
import { syncStandby } from './useWebSocket'

const answer = (state: string) =>
  vi.spyOn(api.standby, 'get').mockResolvedValue({
    state, enabled: true, screensaver_mins: 10, sleep_mins: 20,
  })

beforeEach(() => { useStore.setState({ standby: 'off' }) })
afterEach(() => { vi.restoreAllMocks() })

describe('asking the box where it is', () => {
  it('takes the sleep it missed', async () => {
    answer('sleep')
    await syncStandby()
    expect(useStore.getState().standby).toBe('sleep')
  })

  it('takes the screensaver too', async () => {
    answer('screensaver')
    await syncStandby()
    expect(useStore.getState().standby).toBe('screensaver')
  })

  it('lets go of a standby that ended while the socket was down', async () => {
    // Both directions. A front end that only ever learned to go to sleep would
    // swallow the pad for ever after one missed wake.
    useStore.setState({ standby: 'sleep' })
    answer('active')
    await syncStandby()
    expect(useStore.getState().standby).toBe('off')
  })

  it('says nothing rather than something wrong when the box does not answer', async () => {
    // A failed request is not evidence of anything. Guessing 'off' here would
    // undo a standby the box is really in; guessing 'sleep' would freeze a box
    // that is really awake. Leaving the last known value alone is the only
    // honest option, and the websocket will correct it.
    useStore.setState({ standby: 'screensaver' })
    vi.spyOn(api.standby, 'get').mockRejectedValue(new Error('nope'))
    await syncStandby()
    expect(useStore.getState().standby).toBe('screensaver')
  })

  it('ignores a state it does not recognise', async () => {
    // The backend's vocabulary is 'active' | 'screensaver' | 'sleep'. Anything
    // else is a version mismatch, and mapping the unknown onto 'sleep' would
    // black out a box mid-OTA.
    answer('something-new')
    await syncStandby()
    expect(useStore.getState().standby).toBe('off')
  })
})
