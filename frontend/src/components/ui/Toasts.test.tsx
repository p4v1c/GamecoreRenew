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
import type { ToastsViewProps } from './toasts/types'
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

/**
 * A themed stack.
 *
 * `Toasts` was rendered by `DefaultShell` and was not one of the parts, so a
 * theme that wrote its own tree lost every notification there is — the ROM that
 * finished uploading, the pad that went flat, the offer to map a controller
 * that does not work. Silently, and only on the machine of whoever was standing
 * in front of the TV.
 */
describe('a theme that draws its own toasts', () => {
  /** Renders the same data as text, so the assertions do not depend on a look. */
  const ThemedView = ({ toasts, onDismiss }: ToastsViewProps) => (
    <div>
      {toasts.map(t => (
        <div key={t.id}>
          <span>themed: {t.title}</span>
          {t.action && (
            <button onClick={() => { t.action!.run(); onDismiss(t.id) }}>{t.action.label}</button>
          )}
        </div>
      ))}
    </div>
  )

  it('receives the same events the default stack does', () => {
    render(<Toasts view={ThemedView} />)
    emit('game:failed', { detail: 'RPCS3 exited immediately' })

    expect(screen.getByText('themed: Could not start the game')).toBeTruthy()
  })

  it('replaces the markup and nothing else', () => {
    // The point of the seam: the theme draws, the host still decides what a
    // toast IS. A themed stack cannot quietly drop the one that carries a
    // button, because it never chose which ones exist.
    render(<Toasts view={ThemedView} />)
    emit('gp:connected', { player: 2, label: 'Generic USB Gamepad', unmapped: true })

    expect(screen.getByText('themed: Controller 2 is not recognised')).toBeTruthy()
    expect(screen.queryByText('Controller 2 is not recognised')).toBeNull()

    act(() => { (screen.getByText('Map it now') as HTMLButtonElement).click() })
    expect(useStore.getState().remapRequest).toBe(1)
  })

  it('still hands the HUD what the HUD owns', () => {
    // The handover is the host's call, not the view's. A theme cannot claim a
    // toast the native always-on-top window is supposed to draw over a
    // fullscreen emulator.
    const controllerToast = vi.fn()
    ;(window as { gamecore?: unknown }).gamecore = { controllerToast }

    render(<Toasts view={ThemedView} />)
    emit('gp:connected', { player: 1, label: 'PS4 Controller', unmapped: false })

    expect(controllerToast).toHaveBeenCalledOnce()
    expect(screen.queryByText(/^themed:/)).toBeNull()
  })
})
