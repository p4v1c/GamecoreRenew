/**
 * Waking from Rest mode: the count from the backend, the store, and the shell.
 * The backend is a stubbed fetch; nothing sleeps.
 */
import { render, act, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useStore } from '../store'
import { onResumed, syncWake, resetWakeForTests } from './wake'
import DefaultShell from '../components/DefaultShell'
import type { PowerViewProps } from '../components/modals/power/types'

const answer = (resumes: number) => vi.stubGlobal('fetch', vi.fn(async () => ({
  ok: true, status: 200, statusText: 'OK', json: async () => ({ resting: false, resumes }),
})))

beforeEach(() => {
  resetWakeForTests()
  useStore.setState({ wakeCount: 0, powerPending: null, screen: 'home', modalDepth: 0,
                      sessionGameKey: null, backgroundSessions: [] })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('the wake count', () => {
  it('an announced wake lands on Home and unfreezes the power menu', () => {
    useStore.setState({ screen: 'library', selectedSystemId: 'nes', powerPending: 'rest' })
    onResumed(1)
    const s = useStore.getState()
    expect(s.wakeCount).toBe(1)
    expect(s.screen).toBe('home')
    expect(s.selectedSystemId).toBeNull()
    expect(s.powerPending).toBeNull()
  })

  it('the same wake announced twice replays once', () => {
    onResumed(3)
    onResumed(3)
    expect(useStore.getState().wakeCount).toBe(1)
  })

  it('a wake missed while the socket was down is caught on reconnect', async () => {
    answer(2)
    await syncWake()                    // first connection: nothing to compare
    expect(useStore.getState().wakeCount).toBe(0)
    answer(3)
    await syncWake()                    // reconnect after a sleep
    expect(useStore.getState().wakeCount).toBe(1)
  })

  it('a restarted backend counting from zero is not a wake', async () => {
    answer(5)
    await syncWake()
    answer(0)
    await syncWake()
    expect(useStore.getState().wakeCount).toBe(0)
  })
})

describe('the shell after a wake', () => {
  it('closes the power menu that sent the box to sleep', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, statusText: 'OK', json: async () => [] })))
    let shown = 0
    const PowerView = (_p: PowerViewProps) => { shown++; return <div data-testid="power" /> }
    const Nothing = () => null
    const { queryByTestId } = render(
      <DefaultShell background={Nothing} topbar={Nothing} homeView={Nothing as never}
                    libraryView={Nothing as never} powerView={PowerView} />)
    await act(async () => { window.dispatchEvent(new CustomEvent('gp:power')) })
    expect(queryByTestId('power')).not.toBeNull()
    expect(shown).toBeGreaterThan(0)
    await act(async () => { onResumed(1) })
    await act(async () => { await new Promise(r => setTimeout(r, 400)) })
    expect(queryByTestId('power')).toBeNull()
  })
})
