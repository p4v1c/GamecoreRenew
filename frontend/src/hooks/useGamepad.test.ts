/**
 * The gamepad event bus.
 *
 * Every screen and every theme navigates through the `gp:*` CustomEvents this
 * hook puts on `window`. Two invariants here are not cosmetic:
 *
 *   · while a game is running, everything is suppressed EXCEPT `gp:guide`.
 *     If it is not, an emulator input reaches the UI behind the game — the
 *     power menu opens under a running emulator, or another game launches on
 *     top of the first one.
 *   · `onGp` must really detach. A listener that survives its component fires
 *     against a screen that is gone, and on a box that never restarts its
 *     browser they accumulate for as long as it is switched on.
 *
 * The 60fps poll loop itself is not driven here: it needs requestAnimationFrame
 * and a real Gamepad, which is the "real canvas or timing" category left out on
 * purpose. What is covered is the bus, the keyboard stand-in and the session
 * guard — all reachable without a pad.
 */
import { cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useStore } from '../store'
import { GP_BTN, isPlaying, onGamepadFrame, onGp, useGamepad } from './useGamepad'

beforeEach(() => {
  useStore.setState({ sessionGameKey: null, sessionSystemId: null })
})

afterEach(() => {
  // Unmount every hook this test rendered. Without it each `renderHook` leaves
  // its keydown listener on `window` for the rest of the file and one key
  // press counts as many — which is precisely the leak the unmount test below
  // is meant to catch, so leaving it out would make that test pass for the
  // wrong reason and then fail for a fake one.
  cleanup()
  vi.restoreAllMocks()
})

/** Press a key the way a browser does, and give the hook its listener back. */
function press(key: string, target?: Partial<HTMLElement>) {
  const event = new KeyboardEvent('keydown', { key, cancelable: true, bubbles: true })
  if (target) Object.defineProperty(event, 'target', { value: target })
  window.dispatchEvent(event)
  return event
}

describe('onGp', () => {
  it('delivers the event and its detail', () => {
    const seen: unknown[] = []
    const off = onGp('gp:connected', d => seen.push(d))

    window.dispatchEvent(new CustomEvent('gp:connected', { detail: 'Some Pad' }))
    expect(seen).toEqual(['Some Pad'])
    off()
  })

  it('delivers null for an event with no detail', () => {
    // `new CustomEvent(name)` fills detail with null, not undefined — the
    // handler signature says `detail?: unknown`, so a subscriber testing for
    // undefined would never match a plain button press.
    const seen: unknown[] = []
    const off = onGp('gp:confirm', d => seen.push(d))

    window.dispatchEvent(new CustomEvent('gp:confirm'))
    expect(seen).toEqual([null])
    off()
  })

  it('really detaches, so a dead screen stops hearing the pad', () => {
    let count = 0
    const off = onGp('gp:back', () => { count++ })

    window.dispatchEvent(new CustomEvent('gp:back'))
    off()
    window.dispatchEvent(new CustomEvent('gp:back'))
    expect(count).toBe(1)
  })

  it('keeps two subscribers independent', () => {
    let a = 0, b = 0
    const offA = onGp('gp:menu', () => { a++ })
    const offB = onGp('gp:menu', () => { b++ })

    window.dispatchEvent(new CustomEvent('gp:menu'))
    offA()
    window.dispatchEvent(new CustomEvent('gp:menu'))

    expect([a, b]).toEqual([1, 2])
    offB()
  })
})

describe('isPlaying', () => {
  it('is false with no session and true with one', () => {
    expect(isPlaying()).toBe(false)
    useStore.getState().setSession('some-game', 'some-system')
    expect(isPlaying()).toBe(true)
  })

  it('reads the store synchronously, not through a React render', () => {
    // The poll loop calls this inside requestAnimationFrame, outside React.
    // A subscription-based answer would be one frame stale — which is one
    // frame of UI input reaching a game that has just launched.
    useStore.setState({ sessionGameKey: 'some-game' })
    expect(isPlaying()).toBe(true)
    useStore.setState({ sessionGameKey: null })
    expect(isPlaying()).toBe(false)
  })
})

describe('the keyboard stand-in', () => {
  it('emits the same events the pad does', () => {
    const seen: string[] = []
    const names = ['gp:dpad-up', 'gp:dpad-down', 'gp:dpad-left', 'gp:dpad-right',
                   'gp:confirm', 'gp:back', 'gp:menu', 'gp:power', 'gp:x',
                   'gp:l1', 'gp:r1']
    const offs = names.map(n => onGp(n, () => seen.push(n)))
    renderHook(() => useGamepad())

    for (const key of ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
                       'Enter', 'Escape', 'm', 'p', 'c', 'PageUp', 'PageDown']) {
      press(key)
    }

    expect(new Set(seen)).toEqual(new Set(names))
    offs.forEach(off => off())
  })

  it('accepts the upper-case letter too', () => {
    // Caps lock on a rescue keyboard is not a reason for the box to stop
    // responding.
    let count = 0
    const off = onGp('gp:menu', () => { count++ })
    renderHook(() => useGamepad())

    press('m')
    press('M')
    expect(count).toBe(2)
    off()
  })

  it('never steals a keystroke from a real field', () => {
    // The Wi-Fi password box is on the same screen as the navigation. Typing
    // "m" into it must not open Settings underneath.
    let count = 0
    const off = onGp('gp:menu', () => { count++ })
    renderHook(() => useGamepad())

    for (const tagName of ['INPUT', 'TEXTAREA', 'SELECT']) {
      press('m', { tagName, isContentEditable: false } as Partial<HTMLElement>)
    }
    press('m', { tagName: 'DIV', isContentEditable: true } as Partial<HTMLElement>)

    expect(count).toBe(0)
    off()
  })

  it('ignores a shortcut held with a modifier', () => {
    // Ctrl-P is print, not the power menu.
    let count = 0
    const off = onGp('gp:power', () => { count++ })
    renderHook(() => useGamepad())

    for (const mod of ['metaKey', 'ctrlKey', 'altKey']) {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'p', [mod]: true }))
    }
    expect(count).toBe(0)
    off()
  })

  it('suppresses everything but the guide while a game runs', () => {
    // The invariant. An emulator input reaching the UI behind a running game
    // is how the power menu opens under it.
    const seen: string[] = []
    const offs = ['gp:confirm', 'gp:menu', 'gp:power', 'gp:dpad-up']
      .map(n => onGp(n, () => seen.push(n)))
    renderHook(() => useGamepad())

    useStore.getState().setSession('some-game', 'some-system')
    for (const key of ['Enter', 'm', 'p', 'ArrowUp']) press(key)

    expect(seen).toEqual([])
    offs.forEach(off => off())
  })

  it('stops listening once the hook is unmounted', () => {
    let count = 0
    const off = onGp('gp:confirm', () => { count++ })
    const { unmount } = renderHook(() => useGamepad())

    press('Enter')
    unmount()
    press('Enter')

    expect(count).toBe(1)
    off()
  })

  it('leaves a key it does not map alone', () => {
    // No preventDefault on an unmapped key: a browser shortcut must keep
    // working for whoever is rescuing the box over VNC.
    renderHook(() => useGamepad())
    expect(press('z').defaultPrevented).toBe(false)
    expect(press('Enter').defaultPrevented).toBe(true)
  })
})

describe('onGamepadFrame', () => {
  it('detaches its subscriber', () => {
    // These are the subscribers that must apply isPlaying() themselves — the
    // frame callback sits outside the session guard on purpose, and the L1+R1
    // theme rescue forgetting that is how a box reset its own theme mid-game.
    const cb = vi.fn()
    const off = onGamepadFrame(cb)
    off()
    // Nothing to poll in jsdom, so what is asserted is that detaching is safe
    // and idempotent — a double cleanup happens on every fast screen change.
    expect(() => off()).not.toThrow()
    expect(cb).not.toHaveBeenCalled()
  })
})

describe('the button map', () => {
  it('is the browser standard mapping', () => {
    // Exported for the controller screen, which draws a pad from these
    // indices. They are the W3C standard mapping and are not ours to renumber.
    expect(GP_BTN).toMatchObject({
      A: 0, B: 1, X: 2, Y: 3,
      L1: 4, R1: 5, L2: 6, R2: 7,
      SHARE: 8, OPTIONS: 9,
      DPAD_UP: 12, DPAD_DOWN: 13, DPAD_LEFT: 14, DPAD_RIGHT: 15,
      GUIDE: 16,
    })
  })
})
