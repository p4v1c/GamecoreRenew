/**
 * Getting to the wizard from a sofa.
 *
 * The validation session found it unreachable three ways over, and this covers
 * the second: even where the button was drawn — the fallback view only — it was
 * a plain <button>, selectable with a mouse and nothing else. A controller
 * screen reached with a controller, offering the fix for a broken controller
 * behind a pointer.
 *
 * The gesture lives in GamepadModal rather than in a view, and that is what
 * this file is really pinning. A theme is allowed to leave the button out;
 * what it must not be able to do is make the wizard unreachable, and both
 * shipped themes did exactly that by not destructuring `onRemap`.
 *
 * A HOLD and not a press, because this screen's whole rule is that every press
 * is a test and must only light up its counterpart on the diagram.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, cleanup } from '@testing-library/react'
import GamepadModal from '../GamepadModal'
import { api } from '../../../api'
import { GP_BTN } from '../../../hooks/useGamepad'
import type { GamepadState } from '../../../hooks/useGamepad'

const IDLE: GamepadState = { connected: true, pressed: [], values: [], axes: [0, 0, 0, 0] }

/**
 * The real hook re-renders its consumer on every frame the pad moves, so the
 * stub has to be a hook too — a plain `() => pad` returns the new value only
 * when something ELSE happens to re-render, and then a hold is measured from
 * whenever that was.
 */
let push: ((s: GamepadState) => void) | null = null

vi.mock('../../../hooks/useGamepad', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../../hooks/useGamepad')>()
  const React = await import('react')
  return {
    ...real,
    onGp: () => () => {},
    useGamepadState: () => {
      const [state, set] = React.useState(IDLE)
      React.useEffect(() => { push = set; return () => { push = null } }, [])
      return state
    },
  }
})

async function hold(button: number, down: boolean) {
  const pressed: boolean[] = []
  pressed[button] = down
  await act(async () => { push?.({ ...IDLE, pressed }) })
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.spyOn(api, 'sysinfo').mockResolvedValue({ controllers: [] } as never)
  vi.spyOn(api.controllers, 'devices').mockResolvedValue({ devices: [] } as never)
  // The wizard opens a session the moment it mounts; nothing here is about
  // what it does next, only about whether it was reached at all.
  vi.spyOn(api.controllers.mapping, 'start').mockResolvedValue(
    { ok: false, error: 'not in this test' } as never)
  vi.spyOn(api.controllers.mapping, 'cancel').mockResolvedValue({ ok: true } as never)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

async function mount() {
  render(<GamepadModal onClose={() => {}} />)
  await act(async () => { await Promise.resolve() })
}

async function advance(ms: number) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms) })
}

/** The wizard is up — it fails to start in these tests, which is enough. */
const inWizard = () => screen.queryByText(/wizard could not start/i) !== null

describe('reaching the mapping wizard with the controller', () => {
  it('opens on a sustained hold of the top face button', async () => {
    await mount()
    expect(inWizard()).toBe(false)

    await hold(GP_BTN.Y, true)
    await advance(1200)

    expect(inWizard()).toBe(true)
  })

  it('does not open on a press', async () => {
    await mount()

    await hold(GP_BTN.Y, true)
    await advance(200)
    await hold(GP_BTN.Y, false)
    await advance(3000)

    expect(inWizard()).toBe(false)
  })

  it('leaves every other button to the diagram', async () => {
    await mount()

    await hold(GP_BTN.A, true)
    await advance(3000)

    expect(inWizard()).toBe(false)
  })
})
