/**
 * The power menu: Rest mode first and under the cursor, and the "In the
 * background" row, the route to a suspended session for pads whose guide
 * button never reaches the box (so PS ×2 cannot exist).
 */
import { render, screen, act, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PowerModal from './PowerModal'
import { useStore } from '../../store'

const SUSPENDED = { gameKey: 'crash.cue', systemId: 'duckstation', session: 1, kind: 'game' as const }

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useStore.setState({ backgroundSessions: [], powerPending: null, sessionMenuRequest: 0, asleep: false })
})

const press = (name: string) => act(() => { window.dispatchEvent(new CustomEvent(name)) })

type Seen = { ids: string[]; focusIdx: number; options: { id: string; desc: string }[] }
const spyView = () => {
  const seen: Seen[] = []
  const Spy = (p: { options: { id: string; desc: string }[]; focusIdx: number }) => {
    seen.push({ ids: p.options.map(o => o.id), focusIdx: p.focusIdx, options: p.options })
    return null
  }
  return { seen, Spy, last: () => seen[seen.length - 1] }
}

describe('the power menu', () => {
  it('has no session row when nothing is suspended', () => {
    render(<PowerModal onClose={() => {}} />)
    expect(screen.queryByText('In the background')).toBeNull()
  })

  it('leads with Rest mode, under the cursor, then the other three', () => {
    const { Spy, last } = spyView()
    render(<PowerModal onClose={() => {}} view={Spy as never} />)
    expect(last().ids).toEqual(['rest', 'shutdown', 'restart', 'desktop'])
    expect(last().focusIdx).toBe(0)
  })

  it('opens on Rest mode even when the session row leads', () => {
    useStore.setState({ backgroundSessions: [SUSPENDED] })
    const { Spy, last } = spyView()
    render(<PowerModal onClose={() => {}} view={Spy as never} />)
    expect(last().ids[0]).toBe('sessions')
    expect(last().ids[last().focusIdx]).toBe('rest')
  })

  it('leads with the session row while something is suspended', () => {
    useStore.setState({ backgroundSessions: [SUSPENDED] })
    render(<PowerModal onClose={() => {}} />)
    expect(screen.getByText('In the background')).toBeTruthy()
    // A rule, not a heading, sets the session row apart from the four that end one.
    expect(screen.getByRole('separator')).toBeTruthy()
  })

  it('closes and asks for the session menu on one press', () => {
    // Not a power action: nothing is ended, so there is no second press.
    useStore.setState({ backgroundSessions: [SUSPENDED] })
    const onClose = vi.fn()
    render(<PowerModal onClose={onClose} />)
    press('gp:dpad-up')
    press('gp:confirm')
    expect(onClose).toHaveBeenCalled()
    expect(useStore.getState().sessionMenuRequest).toBe(1)
    expect(useStore.getState().powerPending).toBeNull()
  })

  it('still asks twice before turning off', () => {
    useStore.setState({ backgroundSessions: [SUSPENDED] })
    render(<PowerModal onClose={() => {}} />)
    press('gp:dpad-down')
    press('gp:confirm')
    expect(useStore.getState().powerPending).toBeNull()
    expect(screen.getByText('Turn off?')).toBeTruthy()
    expect(screen.getByText(/again, or/).textContent).toMatch(/to cancel$/)
  })

  it('asks twice, then hands Rest mode to the backend', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, statusText: 'OK',
                                           json: async () => ({ ok: true, forced: 0 }) }))
    vi.stubGlobal('fetch', fetchMock)
    render(<PowerModal onClose={() => {}} />)
    press('gp:confirm')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByText('Rest mode?')).toBeTruthy()
    press('gp:confirm')
    expect(useStore.getState().powerPending).toBe('rest')
    expect(useStore.getState().asleep).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith('/api/power/rest', expect.objectContaining({ method: 'POST' }))
  })

  it('gives the menu back with the reason when Rest mode is refused', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false, status: 503, statusText: 'Service Unavailable',
      json: async () => ({ detail: 'Rest mode is not set up on this box.' }) })))
    const { Spy, last } = spyView()
    render(<PowerModal onClose={() => {}} view={Spy as never} />)
    press('gp:confirm')
    press('gp:confirm')
    await act(async () => { await new Promise(r => setTimeout(r, 0)) })
    expect(useStore.getState().powerPending).toBeNull()
    expect(useStore.getState().asleep).toBe(false)
    expect(last().options[0].desc).toBe('Rest mode is not set up on this box.')
  })

  it('stays black when the request dies with the sleep', async () => {
    // Chromium drops every socket as the box goes down: fetch rejects, no status.
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    const { Spy, last } = spyView()
    render(<PowerModal onClose={() => {}} view={Spy as never} />)
    press('gp:confirm')
    press('gp:confirm')
    await act(async () => { await new Promise(r => setTimeout(r, 0)) })
    expect(useStore.getState().asleep).toBe(true)
    expect(useStore.getState().powerPending).toBe('rest')
    expect(last().options[0].desc).not.toContain('fetch')
  })

  it('moves with left and right as well, for a menu laid out in a row', () => {
    const { Spy, last } = spyView()
    render(<PowerModal onClose={() => {}} view={Spy as never} />)
    press('gp:dpad-right')
    press('gp:dpad-right')
    press('gp:dpad-left')
    expect(last().focusIdx).toBe(1)
  })
})
