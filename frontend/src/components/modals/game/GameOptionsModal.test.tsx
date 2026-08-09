/**
 * The per-game overlay choice, from the sofa.
 *
 * The panel has three answers and two of them look identical on screen when
 * they are applied: "off" draws nothing, and so does "no bezel was found". The
 * whole value of the panel is that it can tell the player which of those two it
 * is, and can turn the first one on and off. A test that only checked pixels
 * would not notice them being confused.
 *
 * The other load-bearing property is that Automatic is stored as the ABSENCE
 * of a choice — `null`, not the string `"auto"`. Writing today's answer down
 * would freeze it: install a bezel pack next week and the game would keep the
 * answer from before it existed.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, cleanup, waitFor } from '@testing-library/react'
import GameOptionsModal from './GameOptionsModal'
import { api } from '../../../api'

const handlers = new Map<string, () => void>()

vi.mock('../../../hooks/useGamepad', () => ({
  onGp: (event: string, handler: () => void) => {
    handlers.set(event, handler)
    return () => handlers.delete(event)
  },
}))

function press(event: string) {
  act(() => { handlers.get(event)?.() })
}

const CHOICES = {
  system_id: 'duckstation',
  rom: 'Crash Bandicoot (USA).cue',
  current: null as string | null,
  resolved: {
    system_id: 'duckstation', source: 'game',
    asset: '/assets/overlays/duckstation/Crash.png',
    hole: { x: 240, y: 0, w: 1440, h: 1080 }, frame: { w: 1920, h: 1080 },
  },
  options: [
    { id: 'Crash Bandicoot (USA).png', label: 'Crash Bandicoot (USA)',
      level: 'game' as const, asset: '/assets/overlays/duckstation/Crash.png' },
    { id: 'duckstation.png', label: 'duckstation',
      level: 'system' as const, asset: '/assets/overlays/duckstation.png' },
  ],
}

beforeEach(() => {
  handlers.clear()
  vi.spyOn(api.overlays, 'choices').mockResolvedValue({ ...CHOICES })
  vi.spyOn(api.overlays, 'choose').mockResolvedValue({
    ok: true, current: null, resolved: CHOICES.resolved,
  })
})

afterEach(() => { cleanup(); vi.restoreAllMocks() })

function open(onClose = () => {}) {
  return render(
    <GameOptionsModal systemId="duckstation" rom="Crash Bandicoot (USA).cue"
                      title="Crash Bandicoot" onClose={onClose} />)
}

describe('what the panel offers', () => {
  it('lists automatic, every bezel that exists, and off', async () => {
    open()
    await screen.findByText('Automatic')
    expect(screen.getByText('This game’s bezel')).toBeTruthy()
    expect(screen.getByText('System bezel')).toBeTruthy()
    expect(screen.getByText('No overlay')).toBeTruthy()
  })

  it('offers only the system bezel when the game has none of its own', async () => {
    vi.spyOn(api.overlays, 'choices').mockResolvedValue({
      ...CHOICES, options: [CHOICES.options[1]],
    })
    open()
    await screen.findByText('System bezel')
    // A row that resolves to nothing when picked is indistinguishable, from a
    // sofa, from a setting that did not save.
    expect(screen.queryByText('This game’s bezel')).toBeNull()
  })

  it('says what Automatic would actually do right now', async () => {
    vi.spyOn(api.overlays, 'choices').mockResolvedValue({
      ...CHOICES,
      resolved: { ...CHOICES.resolved, source: 'system' },
    })
    open()
    // Otherwise the default row is the only one whose effect is invisible.
    await screen.findByText('No bezel for this game — the system’s is used')
  })

  it('says so when the system has no overlay at all', async () => {
    vi.spyOn(api.overlays, 'choices').mockResolvedValue({
      ...CHOICES, options: [],
      resolved: { ...CHOICES.resolved, source: 'none', asset: null, hole: null },
    })
    open()
    await screen.findByText('No overlay is available for this system')
  })
})

describe('making a choice', () => {
  it('sends "off" when the player turns the overlay off', async () => {
    const spy = vi.spyOn(api.overlays, 'choose')
    open()
    await screen.findByText('No overlay')
    screen.getByText('No overlay').closest('button')!.click()
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith('duckstation', 'Crash Bandicoot (USA).cue', 'off'))
  })

  it('sends null — not "auto" — to go back to automatic', async () => {
    const spy = vi.spyOn(api.overlays, 'choose')
    open()
    await screen.findByText('Automatic')
    screen.getByText('Automatic').closest('button')!.click()
    // `null` means "no preference recorded", so the cascade is free to give a
    // different answer once a pack is installed. A stored "auto" would not.
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith('duckstation', 'Crash Bandicoot (USA).cue', null))
  })

  it('sends the bezel filename when a specific one is picked', async () => {
    const spy = vi.spyOn(api.overlays, 'choose')
    open()
    await screen.findByText('System bezel')
    screen.getByText('System bezel').closest('button')!.click()
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith('duckstation', 'Crash Bandicoot (USA).cue',
                                       'duckstation.png'))
  })

  it('drives the same choice from the pad', async () => {
    const spy = vi.spyOn(api.overlays, 'choose')
    open()
    await screen.findByText('Automatic')
    press('gp:dpad-down')       // → this game's bezel
    press('gp:confirm')
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith('duckstation', 'Crash Bandicoot (USA).cue',
                                       'Crash Bandicoot (USA).png'))
  })

  it('cannot be scrolled past the ends of the list', async () => {
    const spy = vi.spyOn(api.overlays, 'choose')
    open()
    await screen.findByText('Automatic')
    for (let i = 0; i < 10; i++) press('gp:dpad-up')
    press('gp:confirm')
    // Still on the first row, not on undefined.
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith('duckstation', 'Crash Bandicoot (USA).cue', null))
  })
})

describe('leaving', () => {
  it('closes on ○', async () => {
    const onClose = vi.fn()
    open(onClose)
    await screen.findByText('Automatic')
    press('gp:back')
    expect(onClose).toHaveBeenCalled()
  })

  it('closes on the button that opened it', async () => {
    // A modal a player cannot leave the way they entered is one they leave by
    // pulling the plug.
    const onClose = vi.fn()
    open(onClose)
    await screen.findByText('Automatic')
    press('gp:r2')
    expect(onClose).toHaveBeenCalled()
  })
})

describe('when the backend does not answer', () => {
  it('says the game still launches, rather than looking broken', async () => {
    vi.spyOn(api.overlays, 'choices').mockRejectedValue(new Error('503'))
    open()
    await screen.findByText(/The overlay settings could not be read/)
    // Off is still reachable: the panel degrades to its fixed rows rather
    // than to an empty box with no way out except ○.
    expect(screen.getByText('No overlay')).toBeTruthy()
  })
})
