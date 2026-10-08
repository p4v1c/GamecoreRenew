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
import { useStore } from '../../../store'
import { GP_BTN } from '../../../hooks/useGamepad'
import type { GamepadState } from '../../../hooks/useGamepad'

const IDLE: GamepadState = { connected: true, index: 0, id: '', mapping: 'standard', pressed: [], values: [], axes: [0, 0, 0, 0] }

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
  vi.spyOn(api.controllers, 'pads').mockResolvedValue({ pads: [] } as never)
  vi.spyOn(api.controllers, 'autoconfig').mockResolvedValue({ enabled: true } as never)
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

describe('which pad the screen reads', () => {
  const DS4 = 'Wireless Controller (STANDARD GAMEPAD Vendor: 054c Product: 09cc)'
  const GEN = 'USB Gamepad (Vendor: 0079 Product: 0006)'
  const roster = (known: string) => ({ pads: [
    { player: 1, name: 'PS4 Controller', kernelName: '', vendor: '054c', product: '09cc', connection: 'Bluetooth',
      battery: 85, charging: false, known: 'sdl', controls: null, analogTriggers: true },
    { player: 2, name: 'USB Gamepad', kernelName: '', vendor: '0079', product: '0006', connection: 'USB',
      battery: null, charging: false, known, controls: null, analogTriggers: true },
  ] })

  beforeEach(() => {
    vi.spyOn(navigator, 'getGamepads').mockReturnValue(
      [{ index: 0, id: DS4, mapping: 'standard' }, { index: 1, id: GEN, mapping: 'standard' }] as never)
  })

  it('shows the pad that pressed □, player 2 here, and marks it', async () => {
    vi.spyOn(api.controllers, 'pads').mockResolvedValue(roster('sdl') as never)
    await mount()
    await act(async () => { push?.({ ...IDLE, index: 1 }) })
    expect(screen.getByText('PLAYER 2')).toBeTruthy()
    expect(document.querySelector('.gcs-pad-roster [data-active="1"]')?.textContent).toContain('USB Gamepad')
  })

  it('switches when another pad is touched', async () => {
    vi.spyOn(api.controllers, 'pads').mockResolvedValue(roster('sdl') as never)
    await mount()
    await act(async () => { push?.({ ...IDLE, index: 1 }) })
    await act(async () => { push?.({ ...IDLE, index: 0 }) })
    expect(screen.getByText('PLAYER 1')).toBeTruthy()
    expect(screen.getByText('Bluetooth · 85%')).toBeTruthy()
  })

  it('names a pad linked to a profile after it, the others by number', async () => {
    vi.spyOn(api.controllers, 'pads').mockResolvedValue(roster('sdl') as never)
    useStore.getState().setPads([], { 1: 'jimmy' })
    try {
      await mount()
      await act(async () => { push?.({ ...IDLE, index: 0 }) })
      expect(screen.getByText('JIMMY')).toBeTruthy()
      expect([...document.querySelectorAll('.gcs-pad-roster b')].map((b) => b.textContent)).toEqual(['jimmy', 'P2'])
    } finally { useStore.getState().setPads([], {}) }
  })

  it('says a pad is not recognised and offers the wizard', async () => {
    vi.spyOn(api.controllers, 'pads').mockResolvedValue(roster('unknown') as never)
    await mount()
    await act(async () => { push?.({ ...IDLE, index: 1 }) })
    expect(screen.getByText(/^Not recognised/)).toBeTruthy()
    expect(screen.getByText('Map this controller')).toBeTruthy()
  })
  it('shows a raw pad by its own button numbers, never as positions', async () => {
    vi.spyOn(navigator, 'getGamepads').mockReturnValue([{ index: 0, id: GEN, mapping: '' }] as never)
    vi.spyOn(api.controllers, 'pads').mockResolvedValue({ pads: [roster('unknown').pads[1]] } as never)
    await mount()
    const pressed = Array(12).fill(false); pressed[4] = true
    await act(async () => { push?.({ ...IDLE, index: 0, mapping: '', pressed }) })
    expect(screen.getByText('B5').getAttribute('data-on')).toBe('1')
    expect(screen.getByText(/raw buttons/)).toBeTruthy()
    expect(screen.queryByText('Select and play')).toBeNull()      // no position legend
  })
})
