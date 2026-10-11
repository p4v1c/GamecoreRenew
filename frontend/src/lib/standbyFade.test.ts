/**
 * Standby stages crossfade instead of cutting, and the screen goes off only
 * once the fade to black is over. See standbyFade.ts.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useStore } from '../store'
import { api } from '../api'
import { fadeToStandby } from './standbyFade'

type Doc = { startViewTransition?: (cb: () => void) => { finished: Promise<void> } }
const doc = document as unknown as Doc

/** A view transition that runs the update at once and finishes when told. */
function fakeTransition() {
  let finish = () => {}
  const start = vi.fn((cb: () => void) => {
    cb()
    return { finished: new Promise<void>((r) => { finish = r }) }
  })
  doc.startViewTransition = start
  return { start, finish: () => finish() }
}

const flush = () => new Promise((r) => setTimeout(r, 0))

let dark: ReturnType<typeof vi.fn>
const win = window as unknown as { gamecore?: unknown }
beforeEach(() => {
  win.gamecore = {}
  useStore.setState({ standby: 'off' })
  dark = vi.fn().mockResolvedValue({})
  vi.spyOn(api.standby, 'dark').mockImplementation(dark)
})
afterEach(() => {
  delete win.gamecore
  delete doc.startViewTransition
  vi.restoreAllMocks()
})

describe('fadeToStandby', () => {
  it('crossfades into the screensaver and out of it', () => {
    const vt = fakeTransition()
    fadeToStandby('screensaver')
    expect(useStore.getState().standby).toBe('screensaver')
    fadeToStandby('off')
    expect(useStore.getState().standby).toBe('off')
    expect(vt.start).toHaveBeenCalledTimes(2)
  })

  it('tells the backend the screen is dark only after the fade', async () => {
    const vt = fakeTransition()
    fadeToStandby('sleep')
    await flush()
    expect(dark).not.toHaveBeenCalled()
    vt.finish()
    await flush()
    expect(dark).toHaveBeenCalledOnce()
  })

  it('keeps the screen on when a press wakes the box mid-fade', async () => {
    const vt = fakeTransition()
    fadeToStandby('sleep')
    useStore.getState().setStandby('off')
    vt.finish()
    await flush()
    expect(dark).not.toHaveBeenCalled()
  })

  it('without view transitions, switches at once and still reports dark', async () => {
    fadeToStandby('sleep')
    expect(useStore.getState().standby).toBe('sleep')
    await flush()
    expect(dark).toHaveBeenCalledOnce()
  })

  it('leaves the answer to the TV window, not a phone', async () => {
    delete win.gamecore
    fadeToStandby('sleep')
    await flush()
    expect(dark).not.toHaveBeenCalled()
  })

  it('honours reduced motion', () => {
    const vt = fakeTransition()
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true } as MediaQueryList)
    fadeToStandby('screensaver')
    expect(vt.start).not.toHaveBeenCalled()
    expect(useStore.getState().standby).toBe('screensaver')
  })
})
