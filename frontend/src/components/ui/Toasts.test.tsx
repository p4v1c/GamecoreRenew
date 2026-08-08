/**
 * The toast that offers the mapping wizard.
 *
 * P1 made the give-up visible in the journal and at "Scan mapping". Neither is
 * where the player is standing: they have just plugged a pad in and it does not
 * work. This toast is, and before this it said "Controller 2 connected" in
 * green for a controller dead in every emulator that matches a device by name.
 *
 * Two things here are load-bearing and easy to lose in a refactor: the offer
 * must not go to the Electron HUD, which draws text and cannot carry a button;
 * and the toast must take pointer events back from a stack that is deliberately
 * click-through. Either one silently turns the offer into decoration.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, cleanup } from '@testing-library/react'
import Toasts from './Toasts'
import { useStore } from '../../store'

/** The handlers Toasts registers, so a test can play a backend event. */
const handlers = new Map<string, (d: Record<string, unknown>) => void>()

vi.mock('../../hooks/useWebSocket', () => ({
  onWsEvent: (event: string, handler: (d: Record<string, unknown>) => void) => {
    handlers.set(event, handler)
    return () => handlers.delete(event)
  },
}))

function emit(event: string, data: Record<string, unknown>) {
  act(() => { handlers.get(event)?.(data) })
}

beforeEach(() => {
  handlers.clear()
  useStore.setState({ remapRequest: 0 })
  delete (window as { gamecore?: unknown }).gamecore
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('the unrecognised-controller toast', () => {
  it('offers the wizard when the backend says the pad is unmapped', () => {
    render(<Toasts />)
    emit('gp:connected', { player: 2, label: 'Generic USB Gamepad', unmapped: true })

    expect(screen.getByText('Controller 2 is not recognised')).toBeTruthy()
    const button = screen.getByText('Map it now')
    act(() => { (button as HTMLButtonElement).click() })

    expect(useStore.getState().remapRequest).toBe(1)
  })

  it('says nothing special for a pad the box can name', () => {
    // The flag has to mean something. If every connection carried the offer,
    // the first person to see it would learn to ignore it.
    render(<Toasts />)
    emit('gp:connected', { player: 1, label: 'PS4 Controller', unmapped: false })

    expect(screen.getByText('Controller 1 connected')).toBeTruthy()
    expect(screen.queryByText('Map it now')).toBeNull()
  })

  it('keeps the offer in-app even when the Electron HUD exists', () => {
    // Every other toast goes to the native always-on-top HUD when it is there.
    // That window draws text and cannot carry a button, so handing it this one
    // would replace a silence with an offer nobody can accept.
    const controllerToast = vi.fn()
    ;(window as { gamecore?: unknown }).gamecore = { controllerToast }

    render(<Toasts />)
    emit('gp:connected', { player: 1, label: 'Generic USB Gamepad', unmapped: true })

    expect(controllerToast).not.toHaveBeenCalled()
    expect(screen.getByText('Map it now')).toBeTruthy()
  })

  it('still hands an ordinary connection to the HUD', () => {
    // The other half: the exception must be narrow, or the HUD stops being the
    // one path for everything else.
    const controllerToast = vi.fn()
    ;(window as { gamecore?: unknown }).gamecore = { controllerToast }

    render(<Toasts />)
    emit('gp:connected', { player: 1, label: 'PS4 Controller', unmapped: false })

    expect(controllerToast).toHaveBeenCalledOnce()
    expect(screen.queryByText('Controller 1 connected')).toBeNull()
  })

  it('takes pointer events back so the button can actually be pressed', () => {
    // The stack is click-through so a toast never steals a press from the
    // screen behind it. A toast that OFFERS something has to take that back,
    // or its button is decorative — and nothing else here would notice.
    render(<Toasts />)
    emit('gp:connected', { player: 1, label: 'Generic USB Gamepad', unmapped: true })

    const card = screen.getByText('Map it now')
      .parentElement!.parentElement as HTMLElement
    expect(card.style.pointerEvents).toBe('auto')
  })

  it('an ordinary toast stays click-through', () => {
    render(<Toasts />)
    emit('gp:connected', { player: 1, label: 'PS4 Controller', unmapped: false })

    const card = screen.getByText('Controller 1 connected')
      .parentElement!.parentElement as HTMLElement
    expect(card.style.pointerEvents).toBe('none')
  })
})
