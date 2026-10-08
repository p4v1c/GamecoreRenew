/**
 * "Who's playing?" appears only with two profiles or more, once per start,
 * and a pick switches the active profile, closing only once it did. It is
 * decided during the boot, so the splash hands over straight to it.
 */
import { render, waitFor, fireEvent, act, cleanup } from '@testing-library/react'
import { it, expect, vi, beforeEach, afterEach } from 'vitest'
import WhoIsPlaying, { shouldAskWhoIsPlaying } from './WhoIsPlaying'
import { useStore } from '../store'
import { bootSteps, resetBootForTests } from '../lib/boot'

const profile = (id: string, name: string) =>
  ({ id, name, color: '#127a6d', avatar: null, created: '', primary: id === 'a' })

let calls: [string, string][] = []
const serve = (profiles: ReturnType<typeof profile>[], session: Record<string, unknown> = {}) => {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: { method?: string }) => {
    calls.push([init?.method ?? 'GET', String(url)])
    const u = String(url)
    const body = u.endsWith('/profiles') ? { active: 'a', profiles, palette: [] }
      : u.endsWith('/games/session') ? session : profiles[1]
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
}
const profileReads = () => calls.filter(([, u]) => u.endsWith('/profiles'))
const press = (gp: string) => act(() => { window.dispatchEvent(new CustomEvent(gp)) })

afterEach(cleanup)
beforeEach(() => { calls = []; sessionStorage.clear(); resetBootForTests() })

it('asks only with two profiles or more', () => {
  expect(shouldAskWhoIsPlaying(null)).toBe(false)
  expect(shouldAskWhoIsPlaying({ active: 'a', profiles: [profile('a', 'Player 1')], palette: [], separate_saves: [] })).toBe(false)
  expect(shouldAskWhoIsPlaying({ active: 'a', profiles: [profile('a', 'P1'), profile('b', 'Sam')], palette: [], separate_saves: [] })).toBe(true)
  // "Log in automatically": the box starts as the last profile.
  expect(shouldAskWhoIsPlaying({ active: 'a', auto_login: true, profiles: [profile('a', 'P1'), profile('b', 'Sam')], palette: [], separate_saves: [] })).toBe(false)
})

it('stays away on a box with one profile, and lets the boot go on', async () => {
  serve([profile('a', 'Player 1')])
  const { container } = render(<WhoIsPlaying interactive={false} />)
  await waitFor(() => expect(bootSteps().who).toBe(true))
  expect(container.textContent).toBe('')
  expect(useStore.getState().modalDepth).toBe(0)
})

it('is drawn during the boot, before the boot may end, and answers only after it', async () => {
  serve([profile('a', 'Player 1'), profile('b', 'Sam')])
  const { rerender, findByText } = render(<WhoIsPlaying interactive={false} />)
  expect(await findByText('Who’s using this controller?')).toBeTruthy()
  // The boot ends only once the question is drawn: the splash then hands
  // over to it, with no frame of the home in between.
  await waitFor(() => expect(bootSteps().who).toBe(true))
  // Under the splash the pad does not answer it yet.
  press('gp:dpad-right'); press('gp:confirm')
  expect(calls.filter(([m]) => m === 'PUT')).toHaveLength(0)
  rerender(<WhoIsPlaying interactive />)
  press('gp:dpad-right'); press('gp:confirm')
  await waitFor(() => expect(calls).toContainEqual(['PUT', '/api/profiles/active']))
})

it('asks once and switches on a pick', async () => {
  serve([profile('a', 'Player 1'), profile('b', 'Sam')])
  const { findByText, container } = render(<WhoIsPlaying interactive />)
  expect(await findByText('Who’s using this controller?')).toBeTruthy()
  // The depth is raised in a passive effect, a task after the commit that
  // findByText sees: wait for it rather than read it in the same tick.
  await waitFor(() => expect(useStore.getState().modalDepth).toBe(1))
  fireEvent.click((await findByText('Sam')).closest('button')!)
  await waitFor(() => expect(calls).toContainEqual(['PUT', '/api/profiles/active']))
  await waitFor(() => expect(container.textContent).toBe(''))
  await waitFor(() => expect(useStore.getState().modalDepth).toBe(0))

  // A theme switch reloads the page; the question is not asked again, and
  // the boot does not wait for the backend to say so.
  resetBootForTests()
  const reads = profileReads().length
  const again = render(<WhoIsPlaying interactive={false} />)
  expect(bootSteps().who).toBe(true)
  await act(async () => {})
  expect(again.container.textContent).toBe('')
  expect(profileReads()).toHaveLength(reads)
})

it('does not cover a game the interface restarted under', async () => {
  serve([profile('a', 'Max'), profile('b', 'Sam')], { game_key: 'mario.nds', session: 3, system_id: 'nds' })
  const { container } = render(<WhoIsPlaying interactive />)
  await waitFor(() => expect(bootSteps().who).toBe(true))
  await act(async () => {})
  expect(container.textContent).toBe('')
})

it('stays open and says why when the switch is refused', async () => {
  serve([profile('a', 'Max'), profile('b', 'Sam')])
  const fetchOk = globalThis.fetch as unknown as (u: string, i?: { method?: string }) => Promise<unknown>
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: { method?: string }) => {
    if (init?.method === 'PUT') {
      calls.push(['PUT', String(url)])
      return { ok: false, status: 409, statusText: 'Conflict',
        json: async () => ({ detail: 'Close mario.nds before switching profile.' }) }
    }
    return fetchOk(url, init)
  }))
  const { findByText } = render(<WhoIsPlaying interactive />)
  fireEvent.click((await findByText('Sam')).closest('button')!)
  expect(await findByText('Close mario.nds before switching profile.')).toBeTruthy()
  expect(await findByText('Who’s using this controller?')).toBeTruthy()
})

it('asks again later when the profiles could not be read at start', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('backend starting') }))
  vi.spyOn(console, 'error').mockImplementation(() => {})
  render(<WhoIsPlaying interactive={false} />)
  // An unreachable backend never holds the boot.
  await waitFor(() => expect(bootSteps().who).toBe(true))
  cleanup()
  serve([profile('a', 'Max'), profile('b', 'Sam')])
  const { findByText } = render(<WhoIsPlaying interactive />)
  expect(await findByText('Who’s using this controller?')).toBeTruthy()
})

it('wears the theme’s dress when the theme brings one', async () => {
  const { ThemeProvider } = await import('./ThemeSurface')
  const { buildSdk } = await import('../lib/themeSdk')
  const { createWhoIsPlaying } = await import('../settings/whoIsPlaying')
  const dressed = createWhoIsPlaying(buildSdk('jelly', { selectTheme: async () => {} }), { skin: 'jelly-who' })
  serve([profile('a', 'Max'), profile('b', 'Sam')])
  const { findByText, container } = render(
    <ThemeProvider value={{ whoIsPlaying: dressed } as never}><WhoIsPlaying interactive /></ThemeProvider>)
  await findByText('Who’s using this controller?')
  expect(container.querySelector('.gcs-who.jelly-who')).toBeTruthy()
  expect(container.querySelector('.gcs-skin-default')).toBeNull()
})

it('waits for the theme to load before asking', async () => {
  const { ThemeProvider } = await import('./ThemeSurface')
  serve([profile('a', 'Max'), profile('b', 'Sam')])
  const { container, rerender, findByText } = render(
    <ThemeProvider value={{ loading: true } as never}><WhoIsPlaying interactive /></ThemeProvider>)
  await waitFor(() => expect(calls).toHaveLength(2))
  await act(async () => {})
  expect(container.textContent).toBe('')
  // Not drawn yet, so the boot is not over either.
  expect(bootSteps().who).toBe(false)
  rerender(<ThemeProvider value={{ loading: false } as never}><WhoIsPlaying interactive /></ThemeProvider>)
  expect(await findByText('Who’s using this controller?')).toBeTruthy()
  await waitFor(() => expect(bootSteps().who).toBe(true))
})
