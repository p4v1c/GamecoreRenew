/**
 * The way back to a suspended game, and why the host owns it.
 *
 * Suspending is reached through a gesture the core reserves — double Home, in
 * RESERVED_EVENTS precisely so no theme can take the one binding that gets a
 * player out of a game. The way back has to be owned the same way. A theme that
 * simply forgot to draw a session bar would otherwise leave a frozen emulator
 * holding several gigabytes of memory with nothing on screen able to resume or
 * close it, and the player's only remaining move would be the power button.
 *
 * So the host always mounts a bar, and a theme exporting `sessionBar` replaces
 * the picture rather than the guarantee.
 */
import { render, screen, act, cleanup, fireEvent } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SessionBar, { type SessionBarProps } from './SessionBar'
import { useStore, type BackgroundSession } from '../store'
import { api } from '../api'

const SUSPENDED: BackgroundSession = {
  gameKey: 'Zelda_(USA).iso', systemId: 'dolphin', session: 1, kind: 'game' }
const APP: BackgroundSession = {
  gameKey: 'stremio', systemId: 'stremio', session: 2, kind: 'app' }

const held = (...s: BackgroundSession[]) =>
  act(() => { useStore.setState({ backgroundSessions: s }) })

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  useStore.setState({ sessionGameKey: null, sessionSystemId: null,
                      backgroundSessions: [], modalDepth: 0 })
})

describe('the host bar', () => {
  it('is not on screen when nothing is suspended', () => {
    render(<SessionBar />)
    expect(screen.queryByRole('region', { name: /suspended/i })).toBeNull()
  })

  it('appears as soon as something is', () => {
    render(<SessionBar />)
    held(SUSPENDED)
    expect(screen.getByRole('region', { name: /suspended/i })).toBeTruthy()
    // The ROM filename is not a title. `Zelda_(USA).iso` is what the box keys
    // the session by; what the player is shown is what they would recognise.
    expect(screen.getByText('Zelda')).toBeTruthy()
  })

  it('says application, not game, when that is what it is', () => {
    // Getting this wrong is the interface talking about a game the player
    // never started. A tile with no ROM launches with game_key === system_id.
    render(<SessionBar />)
    held(APP)
    expect(screen.getByText(/close application/i)).toBeTruthy()
    expect(screen.queryByText(/close game/i)).toBeNull()
  })

  it('resumes the run it is showing, by number', async () => {
    const resume = vi.spyOn(api.games, 'foreground').mockResolvedValue({} as never)
    render(<SessionBar />)
    held(SUSPENDED)
    await act(async () => {
      fireEvent.click(screen.getByText(/resume game/i))
    })
    expect(resume).toHaveBeenCalledWith(1)
  })

  it('closes the run it is showing, by number', async () => {
    const kill = vi.spyOn(api.games, 'kill').mockResolvedValue({} as never)
    render(<SessionBar />)
    held(SUSPENDED)
    await act(async () => {
      fireEvent.click(screen.getByText(/close game/i))
    })
    // By number and not bare: a bare kill ends whatever is on the SCREEN, which
    // while an app is running is the app, not the game the player pointed at.
    expect(kill).toHaveBeenCalledWith(1)
  })
})

describe('a theme that draws its own', () => {
  it('replaces the picture', () => {
    const Themed = ({ sessions }: SessionBarProps) =>
      <div data-testid="themed">{sessions.length} on the ledge</div>
    render(<SessionBar view={Themed} />)
    held(SUSPENDED)
    expect(screen.getByTestId('themed').textContent).toBe('1 on the ledge')
  })

  it('cannot remove the bar by omitting it', () => {
    // The whole guarantee, in one assertion: no `view`, and the bar is still
    // there with a way out of the suspended session.
    render(<SessionBar view={undefined} />)
    held(SUSPENDED)
    expect(screen.getByRole('region', { name: /suspended/i })).toBeTruthy()
    expect(screen.getByText(/close game/i)).toBeTruthy()
  })
})

describe('who owns the pad', () => {
  it('does not claim it while a game is on the screen', () => {
    // A resumed game owns the pad. If the bar still answered ✕ here, one press
    // would both act on the bar and reach the game behind it.
    render(<SessionBar />)
    act(() => {
      useStore.setState({ backgroundSessions: [SUSPENDED], sessionGameKey: 'stremio' })
    })
    expect(screen.getByRole('region', { name: /suspended/i })
      .querySelector('[data-testid]')).toBeNull()
    // `active` is what a theme draws its cursor from; false means "not mine".
    expect(screen.getByText(/resume game/i).getAttribute('disabled')).toBeNull()
  })

  it('does not claim it while a modal is open', () => {
    const Themed = ({ active }: SessionBarProps) =>
      <div data-testid="active">{String(active)}</div>
    render(<SessionBar view={Themed} />)
    act(() => {
      useStore.setState({ backgroundSessions: [SUSPENDED], modalDepth: 1 })
    })
    expect(screen.getByTestId('active').textContent).toBe('false')
  })

  it('claims it when the screen is clear', () => {
    const Themed = ({ active }: SessionBarProps) =>
      <div data-testid="active">{String(active)}</div>
    render(<SessionBar view={Themed} />)
    held(SUSPENDED)
    expect(screen.getByTestId('active').textContent).toBe('true')
  })
})

describe('a theme whose bar throws', () => {
  it('does not take the way back to the suspended game with it', () => {
    // The guarantee, tested at its weakest point. A theme cannot remove the bar
    // by OMITTING it — that was already covered — but it could remove it by
    // CRASHING, which is the same outcome by a route nobody had checked: a
    // frozen emulator holding gigabytes with nothing on screen able to reach it,
    // and the player's only remaining move the power button.
    const Exploding = () => { throw new Error('theme bar blew up') }
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<SessionBar view={Exploding} />)
    held(SUSPENDED)
    expect(screen.getByRole('region', { name: /suspended/i })).toBeTruthy()
    expect(screen.getByText(/close game/i)).toBeTruthy()
  })
})
