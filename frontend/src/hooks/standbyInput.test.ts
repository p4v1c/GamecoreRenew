/**
 * What the pad may do while the screen is off.
 *
 * Reported from the sofa: "pendant le changement d'état je peux me balader
 * avec ma manette même si l'écran est noir, lancer des jeux". Exactly that.
 * The standby overlay is a picture — it covers the screen and stops nothing —
 * and in `sleep` there is not even a picture, because the backend has cut the
 * panel through DPMS. The poll loop went on emitting `gp:*` the whole time, so
 * every screen and every theme went on navigating: the cursor moved, menus
 * opened, and ✕ launched a game onto a television that was switched off.
 *
 * The rule is the one every console has: the first press wakes, and only that.
 * It cannot live in the overlay — Summer draws its own, and a theme that drew
 * none would lose the guard entirely — so it lives at the bus, above every
 * consumer, host and theme alike.
 *
 * The second half is the pad WAKING the box at all. That was the backend's job
 * alone, over evdev, and evdev is exactly what a box whose account is outside
 * the `input` group does not have: gamepad_monitor warns that a refused device
 * is "invisible everywhere", and standby is one of the places. Chromium still
 * sees the pad, so the frontend can ask — and now does.
 *
 * The poll loop needs requestAnimationFrame and a real Gamepad, so it is the
 * keyboard stand-in that is driven here. Both go through the same `emit`,
 * which is where the guard is, and that is the point of putting it there.
 */
import { cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useStore } from '../store'
import { onGp, useGamepad, WAKE_GRACE_MS } from './useGamepad'
import { api } from '../api'
import * as sounds from '../lib/sounds'

let woke: number

beforeEach(() => {
  woke = 0
  useStore.setState({ sessionGameKey: null, sessionSystemId: null, standby: 'off' })
  vi.spyOn(api.standby, 'exit').mockImplementation(async () => { woke++; return { ok: true } })
  vi.spyOn(sounds, 'playSound').mockImplementation(() => {})
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

function press(key = 'ArrowDown') {
  window.dispatchEvent(new KeyboardEvent('keydown', { key, cancelable: true, bubbles: true }))
}

/** Everything the bus can say, so nothing slips through under another name. */
function listenAll() {
  const seen: string[] = []
  const names = ['gp:dpad-up', 'gp:dpad-down', 'gp:dpad-left', 'gp:dpad-right',
    'gp:confirm', 'gp:back', 'gp:y', 'gp:x', 'gp:menu', 'gp:power']
  const offs = names.map(n => onGp(n, () => seen.push(n)))
  return { seen, off: () => offs.forEach(o => o()) }
}

describe('the pad while the box is asleep', () => {
  it('moves nothing on screen', async () => {
    renderHook(() => useGamepad())
    const bus = listenAll()

    useStore.setState({ standby: 'sleep' })
    press('ArrowDown')
    press('Enter')

    expect(bus.seen).toEqual([])
    bus.off()
  })

  it('is silent — no click over a screen that is off', async () => {
    renderHook(() => useGamepad())
    useStore.setState({ standby: 'sleep' })
    press('ArrowDown')
    expect(sounds.playSound).not.toHaveBeenCalled()
  })

  it('asks the box to wake instead', async () => {
    renderHook(() => useGamepad())
    useStore.setState({ standby: 'sleep' })
    press('ArrowDown')
    await Promise.resolve()
    expect(woke).toBe(1)
  })

  it('asks once, however hard the player mashes', async () => {
    // The wake is one HTTP call. Ten presses in a panic must not be ten.
    renderHook(() => useGamepad())
    useStore.setState({ standby: 'sleep' })
    for (let i = 0; i < 10; i++) press('ArrowDown')
    await Promise.resolve()
    expect(woke).toBe(1)
  })

  it('does the same during the slideshow, not only once the screen is off', async () => {
    renderHook(() => useGamepad())
    const bus = listenAll()
    useStore.setState({ standby: 'screensaver' })
    press('ArrowDown')
    await Promise.resolve()

    expect(bus.seen).toEqual([])
    expect(woke).toBe(1)
    bus.off()
  })

  it('gives the pad back the moment the box says it is awake', async () => {
    renderHook(() => useGamepad())
    const bus = listenAll()

    useStore.setState({ standby: 'sleep' })
    press('ArrowDown')
    expect(bus.seen).toEqual([])

    // What the backend's `standby:exit` does to the store.
    useStore.setState({ standby: 'off' })
    press('ArrowDown')
    expect(bus.seen).toEqual(['gp:dpad-down'])
    bus.off()
  })

  it('is readable by a theme, both ways round', async () => {
    // A theme drawing its own standby screen has to read the SAME value, or it
    // keeps its overlay up after the bus has let go — a black rectangle over a
    // live cursor, which is the fault this whole guard prevents. Summer keys
    // its screensaver off exactly this.
    const { buildSdk } = await import('../lib/themeSdk')
    const sdk = buildSdk('test', { selectTheme: async () => {} })
    const nav = sdk.nav as { get: () => Record<string, unknown>; use: typeof useStore }

    useStore.setState({ standby: 'screensaver' })
    expect(nav.get().standby).toBe('screensaver')
    expect(nav.use.getState().standby).toBe('screensaver')

    useStore.setState({ standby: 'off' })
    expect(nav.get().standby).toBe('off')
  })

  it('gives it back on its own if the box never answers', async () => {
    // The failure this must not have. If the websocket is down, or the backend
    // is wedged, `standby:exit` never arrives — and a guard with no way out is
    // a console whose pad has stopped working, with no screen to explain it.
    // So the swallow is bounded: ask, wait, and let go regardless.
    vi.useFakeTimers()
    renderHook(() => useGamepad())
    const bus = listenAll()

    useStore.setState({ standby: 'sleep' })
    press('ArrowDown')
    expect(bus.seen).toEqual([])

    await vi.advanceTimersByTimeAsync(WAKE_GRACE_MS + 50)
    press('ArrowDown')
    expect(bus.seen).toEqual(['gp:dpad-down'])
    bus.off()
  })
})
