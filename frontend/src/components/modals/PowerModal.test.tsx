/**
 * The power menu's "In the background" row: the route to a suspended session
 * for pads whose guide button never reaches the box, so PS ×2 cannot exist.
 */
import { render, screen, act, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PowerModal from './PowerModal'
import { useStore } from '../../store'

const SUSPENDED = { gameKey: 'crash.cue', systemId: 'duckstation', session: 1, kind: 'game' as const }

afterEach(() => {
  cleanup()
  useStore.setState({ backgroundSessions: [], powerPending: null, sessionMenuRequest: 0 })
})

const press = (name: string) => act(() => { window.dispatchEvent(new CustomEvent(name)) })

describe('the power menu', () => {
  it('has no session row when nothing is suspended', () => {
    render(<PowerModal onClose={() => {}} />)
    expect(screen.queryByText('In the background')).toBeNull()
  })

  it('leads with the session row while something is suspended', () => {
    useStore.setState({ backgroundSessions: [SUSPENDED] })
    render(<PowerModal onClose={() => {}} />)
    expect(screen.getByText('In the background')).toBeTruthy()
    expect(screen.getByText('Ending the session')).toBeTruthy()
  })

  it('closes and asks for the session menu on one press', () => {
    // Not a power action: nothing is ended, so there is no second press.
    useStore.setState({ backgroundSessions: [SUSPENDED] })
    const onClose = vi.fn()
    render(<PowerModal onClose={onClose} />)
    press('gp:confirm')
    expect(onClose).toHaveBeenCalled()
    expect(useStore.getState().sessionMenuRequest).toBe(1)
    expect(useStore.getState().powerPending).toBeNull()
  })

  it('still asks twice before shutting down', () => {
    useStore.setState({ backgroundSessions: [SUSPENDED] })
    render(<PowerModal onClose={() => {}} />)
    press('gp:dpad-down')
    press('gp:confirm')
    expect(useStore.getState().powerPending).toBeNull()
    expect(screen.getByText(/press again to shutdown/i)).toBeTruthy()
  })
})
