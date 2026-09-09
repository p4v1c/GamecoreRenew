/**
 * The poll loop itself — the half of `useGamepad` that used to be left out.
 *
 * The existing suite covers the event bus, the keyboard stand-in and the
 * session guard, and says the loop needs "requestAnimationFrame and a real
 * Gamepad". It needs neither to be *real*: it needs them to be ours. So the
 * frame clock, the wall clock and `navigator.getGamepads()` are all driven
 * from here, one frame at a time, and what is asserted is what the box would
 * emit for a given sequence of pad states.
 *
 * That matters because everything this file covers is a defect that was
 * invisible without it:
 *
 *   · a single threshold, so a stick resting near it walked the menu by itself;
 *   · no repeat, so crossing a four-hundred-game library meant four hundred
 *     flicks of the stick;
 *   · `gamepads.find(g => g !== null)`, so the box obeyed whichever pad the
 *     browser listed first for ever — a second player's pad could not take
 *     over, and an unplugged first pad took the interface with it;
 *   · one shared button history, so two pads overwrote each other's edges.
 *
 * What is NOT claimed here: how any of it feels in the hand. The numbers below
 * are the ones the hook ships with, not a measurement of a good stick.
 */
import { cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useStore } from '../store'
import { getActiveGamepadIndex, onGp, useGamepad } from './useGamepad'

// The hook's own numbers. Repeated rather than exported: a test that imports
// the constant it is checking agrees with any value, including a wrong one.
const AXIS_PRESS = 0.55
const AXIS_RELEASE = 0.32
const REPEAT_DELAY_MS = 275
const REPEAT_INTERVAL_MS = 100

type PadSpec = { index: number; buttons?: Record<number, boolean>; axes?: number[] }

/** A Gamepad the way the browser hands one over: dense arrays, every frame. */
function pad({ index, buttons = {}, axes = [0, 0, 0, 0] }: PadSpec): Gamepad {
  const count = 17
  return {
    index,
    id: `pad ${index}`,
    connected: true,
    mapping: 'standard',
    timestamp: 0,
    axes,
    buttons: Array.from({ length: count }, (_, i) => ({
      pressed: buttons[i] ?? false, touched: buttons[i] ?? false, value: buttons[i] ? 1 : 0,
    })),
    vibrationActuator: null,
  } as unknown as Gamepad
}

/**
 * The box, with its clocks in our hands.
 *
 * `requestAnimationFrame` is a queue of one — which is exactly what the hook
 * keeps — so `frame()` runs precisely one poll and leaves the next one
 * pending. `performance.now()` only moves when a test says so, so a repeat
 * interval is a number and not a wait.
 */
function harness() {
  let pending: FrameRequestCallback | null = null
  let handle = 0
  let clock = 1000
  let pads: (Gamepad | null)[] = []

  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    pending = cb
    return ++handle
  })
  vi.stubGlobal('cancelAnimationFrame', () => { pending = null })
  vi.spyOn(performance, 'now').mockImplementation(() => clock)
  vi.spyOn(navigator, 'getGamepads').mockImplementation(() => pads)

  const seen: string[] = []
  const NAMES = ['gp:dpad-up', 'gp:dpad-down', 'gp:dpad-left', 'gp:dpad-right',
    'gp:confirm', 'gp:back', 'gp:menu', 'gp:power', 'gp:guide', 'gp:x', 'gp:y']
  const offs = NAMES.map(name => onGp(name, () => seen.push(name)))

  return {
    seen,
    /** Present these pads to the next poll. */
    connect(...next: (Gamepad | null)[]) { pads = next },
    /** Run one poll. Returns false if the loop is not running. */
    frame() {
      const cb = pending
      if (!cb) return false
      pending = null
      cb(clock)
      return true
    },
    /** Run one poll `ms` later. */
    tick(ms: number) { clock += ms; return this.frame() },
    /** Is the loop still asking for frames? */
    running() { return pending !== null },
    stop() { offs.forEach(off => off()) },
  }
}

let box: ReturnType<typeof harness>

beforeEach(() => {
  useStore.setState({ sessionGameKey: null, sessionSystemId: null, standby: 'off' })
  box = harness()
})

afterEach(() => {
  box.stop()
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

/** Mount the hook and settle the first frame, which only takes a bearing. */
function start(...pads: (Gamepad | null)[]) {
  const view = renderHook(() => useGamepad())
  box.connect(...pads)
  box.frame()
  return view
}

describe('reading the pad', () => {
  it('polls navigator.getGamepads() every frame', () => {
    start(pad({ index: 0 }))
    expect(navigator.getGamepads).toHaveBeenCalled()
    const before = (navigator.getGamepads as ReturnType<typeof vi.fn>).mock.calls.length
    box.frame()
    expect((navigator.getGamepads as ReturnType<typeof vi.fn>).mock.calls.length)
      .toBeGreaterThan(before)
  })

  it('keeps asking for frames, and stops when the hook goes', () => {
    const view = start(pad({ index: 0 }))
    expect(box.running()).toBe(true)
    view.unmount()
    expect(box.running()).toBe(false)
  })

  it('survives a browser with no Gamepad API at all', () => {
    // Not hypothetical: the hook runs in a plain browser during theme review,
    // and `navigator.getGamepads` is absent in more of them than one expects.
    vi.spyOn(navigator, 'getGamepads').mockImplementation(
      undefined as unknown as () => (Gamepad | null)[])
    Object.defineProperty(navigator, 'getGamepads', { value: undefined, configurable: true })
    const view = renderHook(() => useGamepad())
    expect(() => box.frame()).not.toThrow()
    view.unmount()
  })
})

describe('buttons', () => {
  it('emits once on the press, not once per frame it is held', () => {
    start(pad({ index: 0 }))
    box.connect(pad({ index: 0, buttons: { 0: true } }))
    box.frame()
    box.frame()
    box.frame()
    expect(box.seen).toEqual(['gp:confirm'])
  })

  it('emits again once it has been released and pressed anew', () => {
    start(pad({ index: 0 }))
    box.connect(pad({ index: 0, buttons: { 0: true } }))
    box.frame()
    box.connect(pad({ index: 0 }))
    box.frame()
    box.connect(pad({ index: 0, buttons: { 0: true } }))
    box.frame()
    expect(box.seen).toEqual(['gp:confirm', 'gp:confirm'])
  })

  it('takes a bearing on a pad it has never seen, rather than reporting it', () => {
    // A pad announces its whole state as it arrives, and a Bluetooth pad that
    // re-pairs itself overnight does it again. A button that reads as held in
    // that first frame is not a press anybody made.
    renderHook(() => useGamepad())
    box.connect(pad({ index: 0, buttons: { 0: true } }))
    box.frame()
    box.frame()
    expect(box.seen).toEqual([])
  })

  it('says nothing at all while a game is running, except the guide', () => {
    start(pad({ index: 0 }))
    useStore.setState({ sessionGameKey: 'zelda.iso', sessionSystemId: 'dolphin' })
    box.connect(pad({ index: 0, buttons: { 0: true, 9: true } }))
    box.frame()
    expect(box.seen).toEqual([])
  })
})

describe('the stick, and the threshold it is read against', () => {
  it('moves at once when it is pushed past the press threshold', () => {
    start(pad({ index: 0 }))
    box.connect(pad({ index: 0, axes: [AXIS_PRESS, 0, 0, 0] }))
    box.frame()
    expect(box.seen).toEqual(['gp:dpad-right'])
  })

  it('ignores a stick that never leaves the drift band', () => {
    // The defect this replaces: one threshold, so a stick resting anywhere
    // near it crossed back and forth on sensor noise and the menu walked by
    // itself with nobody touching the box.
    start(pad({ index: 0 }))
    for (const travel of [0.1, 0.3, 0.5, 0.54, 0.2, 0.45]) {
      box.connect(pad({ index: 0, axes: [travel, 0, 0, 0] }))
      box.tick(16)
    }
    expect(box.seen).toEqual([])
  })

  it('holds the direction across the hysteresis band, and ends it below the release', () => {
    start(pad({ index: 0 }))
    box.connect(pad({ index: 0, axes: [0.9, 0, 0, 0] }))
    box.frame()
    expect(box.seen).toEqual(['gp:dpad-right'])

    // Falling back to 0.4 is inside the band: still held, so still no *new*
    // direction — and coming back up to 0.9 is not a new one either.
    box.connect(pad({ index: 0, axes: [0.4, 0, 0, 0] }))
    box.frame()
    box.connect(pad({ index: 0, axes: [0.9, 0, 0, 0] }))
    box.frame()
    expect(box.seen).toEqual(['gp:dpad-right'])

    // Below the release threshold the direction is over, and pushing again is
    // a fresh press that moves immediately.
    box.connect(pad({ index: 0, axes: [AXIS_RELEASE - 0.01, 0, 0, 0] }))
    box.frame()
    box.connect(pad({ index: 0, axes: [0.9, 0, 0, 0] }))
    box.frame()
    expect(box.seen).toEqual(['gp:dpad-right', 'gp:dpad-right'])
  })

  it('reads all four directions off the left stick', () => {
    start(pad({ index: 0 }))
    const push = (axes: number[]) => {
      box.connect(pad({ index: 0, axes }))
      box.frame()
      box.connect(pad({ index: 0, axes: [0, 0, 0, 0] }))
      box.frame()
    }
    push([-0.9, 0, 0, 0])
    push([0, -0.9, 0, 0])
    push([0, 0.9, 0, 0])
    expect(box.seen).toEqual(['gp:dpad-left', 'gp:dpad-up', 'gp:dpad-down'])
  })

  it('ignores the right stick, which is not navigation', () => {
    start(pad({ index: 0 }))
    box.connect(pad({ index: 0, axes: [0, 0, 0.9, -0.9] }))
    box.frame()
    expect(box.seen).toEqual([])
  })

  it('lets go of a held direction when a game takes the stick', () => {
    start(pad({ index: 0 }))
    box.connect(pad({ index: 0, axes: [0.9, 0, 0, 0] }))
    box.frame()
    useStore.setState({ sessionGameKey: 'zelda.iso', sessionSystemId: 'dolphin' })
    box.tick(REPEAT_DELAY_MS + REPEAT_INTERVAL_MS * 5)
    useStore.setState({ sessionGameKey: null, sessionSystemId: null })
    // Coming back with the stick still over must not inherit the repeat, but
    // it is a direction that is newly held again as far as the menu is
    // concerned, so it moves once.
    box.tick(16)
    expect(box.seen).toEqual(['gp:dpad-right', 'gp:dpad-right'])
  })
})

describe('holding a direction', () => {
  it('moves immediately, waits, then repeats', () => {
    start(pad({ index: 0 }))
    const held = pad({ index: 0, axes: [0.9, 0, 0, 0] })
    box.connect(held)
    box.frame()
    expect(box.seen).toEqual(['gp:dpad-right'])

    // Nothing during the initial delay: a single flick has to stay one step.
    box.tick(REPEAT_DELAY_MS - 50)
    expect(box.seen).toEqual(['gp:dpad-right'])

    box.tick(60)
    expect(box.seen).toHaveLength(2)

    // Then at the repeat rate, not at the frame rate.
    box.tick(REPEAT_INTERVAL_MS - 20)
    expect(box.seen).toHaveLength(2)
    box.tick(30)
    expect(box.seen).toHaveLength(3)
  })

  it('crosses a long library without letting go', () => {
    start(pad({ index: 0 }))
    box.connect(pad({ index: 0, axes: [0, 0.9, 0, 0] }))
    box.frame()
    for (let i = 0; i < 40; i++) box.tick(REPEAT_INTERVAL_MS)
    // One immediate step, one after the initial delay, then one per interval.
    expect(box.seen.length).toBeGreaterThan(30)
    expect(new Set(box.seen)).toEqual(new Set(['gp:dpad-down']))
  })

  it('flicks straight across without waiting out the old repeat', () => {
    start(pad({ index: 0 }))
    box.connect(pad({ index: 0, axes: [0.9, 0, 0, 0] }))
    box.frame()
    box.connect(pad({ index: 0, axes: [-0.9, 0, 0, 0] }))
    box.tick(16)
    expect(box.seen).toEqual(['gp:dpad-right', 'gp:dpad-left'])
  })

  it('does not carry a repeat over from one axis to the other', () => {
    start(pad({ index: 0 }))
    box.connect(pad({ index: 0, axes: [0.9, 0.9, 0, 0] }))
    box.frame()
    expect(box.seen).toEqual(['gp:dpad-right', 'gp:dpad-down'])
    box.tick(REPEAT_DELAY_MS + 10)
    expect(box.seen).toEqual(['gp:dpad-right', 'gp:dpad-down',
      'gp:dpad-right', 'gp:dpad-down'])
  })
})

describe('more than one pad', () => {
  it('obeys the pad that is being used, not the one listed first', () => {
    start(pad({ index: 0 }), pad({ index: 1 }))
    expect(getActiveGamepadIndex()).toBe(0)

    box.connect(pad({ index: 0 }), pad({ index: 1, buttons: { 0: true } }))
    box.frame()
    expect(getActiveGamepadIndex()).toBe(1)
    // The press that took control is a real press and is delivered. Asking a
    // second player to press twice — once to be noticed, once to act — is the
    // kind of thing nobody ever discovers is deliberate.
    expect(box.seen).toEqual(['gp:confirm'])
  })

  it('does not let a drifting stick take the box from the pad in someone’s hands', () => {
    // The one that matters. A worn stick sits off-centre for ever; a rule that
    // tested the level rather than the crossing would hand it the box on every
    // frame, and the player's own pad would go dead in their hands.
    start(pad({ index: 0 }), pad({ index: 1 }))
    for (let i = 0; i < 30; i++) {
      box.connect(pad({ index: 0 }), pad({ index: 1, axes: [0.45 + (i % 3) * 0.02, 0, 0, 0] }))
      box.tick(16)
    }
    expect(getActiveGamepadIndex()).toBe(0)
    expect(box.seen).toEqual([])
  })

  it('does not let a stick already over the threshold keep re-taking it', () => {
    // Even a stick stuck past the press threshold claims once, on the crossing,
    // and then never again — so the player can take the box straight back.
    start(pad({ index: 0 }), pad({ index: 1 }))
    box.connect(pad({ index: 0 }), pad({ index: 1, axes: [0.9, 0, 0, 0] }))
    box.tick(16)
    expect(getActiveGamepadIndex()).toBe(1)

    box.connect(pad({ index: 0, buttons: { 1: true } }), pad({ index: 1, axes: [0.9, 0, 0, 0] }))
    box.tick(16)
    expect(getActiveGamepadIndex()).toBe(0)

    for (let i = 0; i < 20; i++) {
      box.connect(pad({ index: 0 }), pad({ index: 1, axes: [0.9, 0, 0, 0] }))
      box.tick(16)
    }
    expect(getActiveGamepadIndex()).toBe(0)
  })

  it('judges each pad against its own last frame', () => {
    // One shared history meant the pad nobody was holding rewrote the record
    // the played one was compared against, and held buttons read as pressed
    // again every other frame.
    start(pad({ index: 0, buttons: { 0: true } }), pad({ index: 1 }))
    for (let i = 0; i < 6; i++) {
      box.connect(pad({ index: 0, buttons: { 0: true } }), pad({ index: 1, buttons: { 3: true } }))
      box.tick(16)
    }
    // Pad 1's press takes the box once; pad 0 holding ✕ throughout says
    // nothing, because it was already down when it was first seen.
    expect(box.seen).toEqual(['gp:y'])
    expect(getActiveGamepadIndex()).toBe(1)
  })

  it('leaves the gaps the browser leaves', () => {
    // getGamepads() is sparse: unplugging pad 0 of two leaves a null in slot 0
    // and does NOT renumber pad 1.
    start(null, pad({ index: 1 }))
    expect(getActiveGamepadIndex()).toBe(1)
    box.connect(null, pad({ index: 1, buttons: { 0: true } }))
    box.frame()
    expect(box.seen).toEqual(['gp:confirm'])
  })
})

describe('unplugging and plugging back in', () => {
  it('hands the box to whatever pad is left', () => {
    start(pad({ index: 0 }), pad({ index: 1 }))
    expect(getActiveGamepadIndex()).toBe(0)

    box.connect(null, pad({ index: 1 }))
    box.frame()
    expect(getActiveGamepadIndex()).toBe(1)

    // And it works — an interface with a pad connected must never be stuck.
    box.connect(null, pad({ index: 1, axes: [0, -0.9, 0, 0] }))
    box.frame()
    expect(box.seen).toEqual(['gp:dpad-up'])
  })

  it('has no pad, and no opinion, when the last one goes', () => {
    start(pad({ index: 0 }))
    box.connect()
    box.frame()
    expect(getActiveGamepadIndex()).toBe(null)
    expect(() => box.frame()).not.toThrow()
  })

  it('does not deliver the state a returning pad arrives holding', () => {
    // The index is handed to the next pad to connect. History left behind on
    // it reads on the new pad as a button that was already down — or as one
    // being released — so the slot is forgotten completely.
    start(pad({ index: 0, buttons: { 0: true } }))
    box.connect(pad({ index: 0, buttons: { 0: true } }))
    box.frame()
    box.connect()
    box.frame()

    box.connect(pad({ index: 0, buttons: { 0: true } }))
    box.frame()
    box.frame()
    expect(box.seen).toEqual([])

    // And it is live again: releasing and pressing is a press.
    box.connect(pad({ index: 0 }))
    box.frame()
    box.connect(pad({ index: 0, buttons: { 0: true } }))
    box.frame()
    expect(box.seen).toEqual(['gp:confirm'])
  })

  it('drops a direction that was being repeated when the pad went', () => {
    start(pad({ index: 0 }))
    box.connect(pad({ index: 0, axes: [0.9, 0, 0, 0] }))
    box.frame()
    expect(box.seen).toEqual(['gp:dpad-right'])

    box.connect()
    box.tick(REPEAT_DELAY_MS + REPEAT_INTERVAL_MS * 4)
    expect(box.seen).toEqual(['gp:dpad-right'])

    // A pad arriving with the stick already over takes a bearing, then reads
    // it as newly held — one move, not a resumed repeat.
    box.connect(pad({ index: 0, axes: [0.9, 0, 0, 0] }))
    box.tick(16)
    box.tick(16)
    expect(box.seen).toEqual(['gp:dpad-right', 'gp:dpad-right'])
  })

  it('announces arrivals and departures without waking a sleeping box', () => {
    const news: string[] = []
    const offs = [onGp('gp:connected', d => news.push(`in:${d}`)),
      onGp('gp:disconnected', () => news.push('out'))]
    start(pad({ index: 0 }))
    useStore.setState({ standby: 'sleep' })

    window.dispatchEvent(Object.assign(
      new Event('gamepadconnected'), { gamepad: pad({ index: 1 }) }))
    window.dispatchEvent(Object.assign(
      new Event('gamepaddisconnected'), { gamepad: pad({ index: 1 }) }))

    // A pad re-pairing itself in the night is not somebody asking for the box.
    expect(news).toEqual(['in:pad 1', 'out'])
    expect(useStore.getState().standby).toBe('sleep')
    offs.forEach(off => off())
  })
})

describe('cleanup', () => {
  it('stops polling, and forgets which pad was active', () => {
    const view = start(pad({ index: 0 }), pad({ index: 1 }))
    box.connect(pad({ index: 0 }), pad({ index: 1, buttons: { 0: true } }))
    box.frame()
    expect(getActiveGamepadIndex()).toBe(1)

    view.unmount()
    expect(getActiveGamepadIndex()).toBe(null)
    expect(box.running()).toBe(false)
  })

  it('leaves nothing for the next mount to inherit', () => {
    // The pad state is module-level so `getActiveGamepadIndex()` can be read
    // without a hook. That is exactly why unmounting has to clear it: a second
    // mount starting against the first one's history sees presses nobody made.
    const first = start(pad({ index: 0, buttons: { 0: true } }))
    box.connect(pad({ index: 0, buttons: { 0: true } }))
    box.frame()
    first.unmount()

    renderHook(() => useGamepad())
    box.connect(pad({ index: 0, buttons: { 0: true } }))
    box.frame()
    box.frame()
    expect(box.seen).toEqual([])
  })

  it('does not keep listening to the window after the screen is gone', () => {
    const view = start(pad({ index: 0 }))
    view.unmount()
    const event = new KeyboardEvent('keydown', { key: 'ArrowDown', cancelable: true })
    window.dispatchEvent(event)
    expect(box.seen).toEqual([])
    expect(event.defaultPrevented).toBe(false)
  })
})
