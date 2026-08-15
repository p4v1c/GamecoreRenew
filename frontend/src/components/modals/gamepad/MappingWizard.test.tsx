/**
 * The wizard's four gestures.
 *
 * Everything on this screen is driven by a controller the box does not
 * understand yet, so there is no second button to reach for: press, hold,
 * double-press and wait are the entire vocabulary, and all four are decided
 * here from the raw press/release edges the backend streams.
 *
 * That makes this logic worth a test on its own. The failure it guards against
 * is not a crash — it is a wizard that records the wrong thing and saves it: a
 * stick still deflected from the previous step filling the next three, or a
 * hold that also counts as a press so a missing button gets bound to whatever
 * the player held to skip it.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, cleanup } from '@testing-library/react'
import MappingWizard from './MappingWizard'
import { api } from '../../../api'

const STEPS = [
  { field: 'a', kind: 'button' as const, label: 'A / Cross' },
  { field: 'b', kind: 'button' as const, label: 'B / Circle' },
  { field: 'lefttrigger', kind: 'axis' as const, label: 'Left trigger' },
]

/** The socket the component opens, captured so a test can push events. */
let socket: FakeSocket

class FakeSocket {
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  closed = false
  close() { this.closed = true }
  send(event: string, data: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify({ event, data }) })
  }
}

let committed: { bindings: Record<string, string>; name: string } | null = null

beforeEach(() => {
  vi.useFakeTimers()
  committed = null
  socket = new FakeSocket()
  vi.spyOn(api.controllers.mapping, 'start').mockResolvedValue({
    ok: true, session: 's1', controller: 'Generic Pad',
    guids: ['0300aaaa'], nodes: ['/dev/input/event9'],
    steps: STEPS, optional: ['guide'],
  })
  vi.spyOn(api.controllers.mapping, 'socket')
    .mockImplementation(() => socket as unknown as WebSocket)
  vi.spyOn(api.controllers.mapping, 'cancel').mockResolvedValue({ ok: true })
  vi.spyOn(api.controllers.mapping, 'commit')
    .mockImplementation(async (bindings, name) => {
      committed = { bindings, name: name ?? '' }
      return { ok: true, lines: ['0300aaaa,Generic Pad,a:b0,platform:Linux,'],
               bindings: Object.keys(bindings).length, missing: [] }
    })
})

afterEach(() => {
  // vitest runs without `globals`, so @testing-library/react never registers
  // its own afterEach — without this every render stays in the document and
  // the queries below match the PREVIOUS test's screen.
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

/** Let the start() promise resolve and the socket be installed. */
async function open() {
  render(<MappingWizard onClose={() => {}} />)
  await act(async () => { await Promise.resolve() })
}

/** Advance past the settle window between steps. */
function settle() {
  act(() => { vi.advanceTimersByTime(400) })
}

function press(binding: string, signed = binding) {
  act(() => { socket.send('input', { binding, signed, pressed: true, kind: 'button' }) })
}

function release(binding: string) {
  act(() => { socket.send('input', { binding, signed: binding, pressed: false, kind: 'button' }) })
}

function tap(binding: string, signed = binding) {
  press(binding, signed)
  act(() => { vi.advanceTimersByTime(60) })
  release(binding)
}

/** The last step now leads to a review screen; confirm it and let commit run. */
async function saveFromReview() {
  act(() => { screen.getByText('Save').click() })
  await act(async () => { await Promise.resolve() })
}

describe('the mapping wizard', () => {
  it('asks for the first step once the session is open', async () => {
    await open()
    expect(screen.getByText('A / Cross')).toBeTruthy()
    expect(screen.getByText('1 / 3')).toBeTruthy()
  })

  it('records a short press and advances', async () => {
    await open()
    tap('b0')
    expect(screen.getByText('B / Circle')).toBeTruthy()
    expect(screen.getByText('2 / 3')).toBeTruthy()
  })

  it('skips the step when the button is HELD', async () => {
    // The pad does not have this button. A hold rather than a second button,
    // because there is no second button we can trust yet — and it must NOT
    // also record the button the player held to say "absent".
    await open()
    press('b0')
    act(() => { vi.advanceTimersByTime(1000) })

    expect(screen.getByText('B / Circle')).toBeTruthy()
    release('b0')
    settle()
    tap('b1')
    settle()
    tap('a2', '+a2')
    await saveFromReview()

    expect(committed?.bindings).toEqual({ b: 'b1', lefttrigger: '+a2' })
    expect(committed?.bindings.a).toBeUndefined()
  })

  it('undoes a step when its own input is pressed again', async () => {
    // A plain double-press cannot coexist with the settle window — the first
    // press starts the window and the second is swallowed as bleed. Tying undo
    // to the input just recorded is what resolves it.
    await open()
    tap('b0')                       // a := b0
    settle()
    tap('b1')                       // b := b1, now on lefttrigger
    expect(screen.getByText('3 / 3')).toBeTruthy()

    act(() => { vi.advanceTimersByTime(100) })
    tap('b1')                       // the same input again, within UNDO_MS

    expect(screen.getByText('B / Circle')).toBeTruthy()
    settle()
    tap('b9')                       // re-record b
    settle()
    tap('a2', '+a2')
    await saveFromReview()

    expect(committed?.bindings.b).toBe('b9')
  })

  it('reviews before writing anything, and can still go back from there', async () => {
    // Committing on the final press would make the last button the one binding
    // that can never be corrected: no screen left to undo from, file already
    // written.
    await open()
    tap('b0'); settle()
    tap('b1'); settle()
    tap('a2', '+a2')

    expect(screen.getByText('Check it over')).toBeTruthy()
    expect(committed).toBeNull()

    act(() => { screen.getByText('Back one step').click() })
    expect(screen.getByText('Left trigger')).toBeTruthy()
    expect(committed).toBeNull()
  })

  it('saves from review when the button captured as A is pressed', async () => {
    // The first end-to-end proof the capture is right, made before anything is
    // written, using the only binding the box can be sure of at that point.
    await open()
    tap('b0'); settle()
    tap('b1'); settle()
    tap('a2', '+a2')
    expect(screen.getByText('Check it over')).toBeTruthy()

    act(() => { vi.advanceTimersByTime(800) })
    tap('b0')                       // what the player said was A
    await act(async () => { await Promise.resolve() })

    expect(committed?.bindings.a).toBe('b0')
    expect(screen.getByText('Your controller is mapped')).toBeTruthy()
  })

  it('ignores input during the settle window after a step', async () => {
    // The bug this exists for: a stick pushed for one axis is STILL deflected
    // when the next step comes up, so one push fills three steps in a row.
    await open()
    tap('b0')
    tap('b7')                       // arrives immediately — must be ignored

    expect(screen.getByText('B / Circle')).toBeTruthy()
    expect(screen.getByText('2 / 3')).toBeTruthy()
  })

  it('keeps the sign for a trigger and drops it for a button', async () => {
    // A trigger resting at its minimum and a stick resting at centre produce
    // the same event; only the step being asked for knows which.
    await open()
    tap('b0', '+b0')
    settle()
    tap('b1')
    settle()
    tap('a2', '+a2')
    await saveFromReview()

    expect(committed?.bindings).toEqual({ a: 'b0', b: 'b1', lefttrigger: '+a2' })
  })

  it('commits once every step is answered and shows the line', async () => {
    await open()
    tap('b0'); settle()
    tap('b1'); settle()
    tap('a2', '+a2')
    await saveFromReview()

    expect(committed).not.toBeNull()
    expect(screen.getByText('Your controller is mapped')).toBeTruthy()
    expect(screen.getByText(/mdqinc\/SDL_GameControllerDB/)).toBeTruthy()
  })

  it('closes the session when the screen goes away', async () => {
    // A session left open holds file descriptors on /dev/input, and the box is
    // a device someone walks away from mid-wizard.
    const { unmount } = render(<MappingWizard onClose={() => {}} />)
    await act(async () => { await Promise.resolve() })
    unmount()

    expect(socket.closed).toBe(true)
    expect(api.controllers.mapping.cancel).toHaveBeenCalled()
  })

  it('says so when the backend refuses to start', async () => {
    vi.mocked(api.controllers.mapping.start).mockResolvedValue({
      ok: false, error: 'connect exactly one controller',
    })
    await open()

    expect(screen.getByText('The wizard could not start')).toBeTruthy()
    expect(screen.getByText('connect exactly one controller')).toBeTruthy()
  })

  // ── the last screen ────────────────────────────────────────────────────────
  //
  // Reported by the owner after running the wizard end to end: "la dernière
  // partie Done ou Copy & contribute, je n'ai pas pu le sélectionner avec mon
  // joystick ou pad directionnel, j'ai dû le faire avec la souris."
  //
  // Every other screen here is driven by the pad. This one had no handling at
  // all — the socket handler fell through `if (!current) return`, because past
  // the last step there is no current step. So a wizard whose premise is "no
  // keyboard, and nothing may depend on a binding" ended on a mouse, on the one
  // screen where the box knows the pad best.

  /** Answer every step, then confirm the review, landing on the last screen. */
  async function reachTheEnd() {
    await open()
    tap('b0'); settle()          // a
    tap('b1'); settle()          // b
    tap('a2', '+a2'); settle()   // lefttrigger
    await saveFromReview()
    settle()                     // past the window that opens with the screen
  }

  it('closes from the last screen with the button captured as A', async () => {
    let closed = false
    render(<MappingWizard onClose={() => { closed = true }} />)
    await act(async () => { await Promise.resolve() })
    tap('b0'); settle()
    tap('b1'); settle()
    tap('a2', '+a2'); settle()
    await saveFromReview()
    settle()
    expect(screen.getByText('Your controller is mapped')).toBeTruthy()

    tap('b0')                    // the input the owner told us was A

    expect(closed).toBe(true)
  })

  it('moves between the two buttons with the captured D-pad', async () => {
    // jsdom ships no clipboard, and the component already guards for that with
    // `navigator.clipboard?.` — a box in a kiosk without one must not crash on
    // the way out. Stubbed here so the assertion has something to read.
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText }, configurable: true,
    })

    // Nothing here is a glyph table: `dpleft`/`dpright` are whatever the owner
    // pressed for those steps, which is the only thing the box can promise.
    vi.mocked(api.controllers.mapping.start).mockResolvedValue({
      ok: true, session: 's1', controller: 'Generic Pad',
      guids: ['0300aaaa'], nodes: ['/dev/input/event9'],
      steps: [{ field: 'a', kind: 'button', label: 'A / Cross' },
              { field: 'dpleft', kind: 'button', label: 'D-pad left' },
              { field: 'dpright', kind: 'button', label: 'D-pad right' }],
      optional: [],
    })
    await open()
    tap('b0'); settle()
    tap('h0.8'); settle()
    tap('h0.2'); settle()
    await saveFromReview()
    settle()

    tap('h0.8')                  // move to "Copy & contribute"
    tap('b0')                    // and choose it

    expect(writeText).toHaveBeenCalledWith(
      '0300aaaa,Generic Pad,a:b0,platform:Linux,')
  })

  it('does not act on input that bled in from the last capture step', async () => {
    // A trigger still deflected when Save fires must not press the button that
    // closes the wizard before a word of it has been read.
    let closed = false
    render(<MappingWizard onClose={() => { closed = true }} />)
    await act(async () => { await Promise.resolve() })
    tap('b0'); settle()
    tap('b1'); settle()
    tap('a2', '+a2'); settle()
    await saveFromReview()

    tap('b0')                    // inside the settle window this screen opens

    expect(closed).toBe(false)
  })
})
