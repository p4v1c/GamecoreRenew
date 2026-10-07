/**
 * "Who's playing?" appears only with two profiles or more, once per start,
 * and a pick switches the active profile, closing only once it did.
 */
import { render, waitFor, fireEvent, act, cleanup } from '@testing-library/react'
import { it, expect, vi, beforeEach, afterEach } from 'vitest'
import WhoIsPlaying, { shouldAskWhoIsPlaying } from './WhoIsPlaying'
import { useStore } from '../store'

const profile = (id: string, name: string) =>
  ({ id, name, color: '#127a6d', avatar: null, created: '', primary: id === 'a' })

let calls: [string, string][] = []
const serve = (profiles: ReturnType<typeof profile>[]) => {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: { method?: string }) => {
    calls.push([init?.method ?? 'GET', String(url)])
    const body = String(url).endsWith('/profiles') ? { active: 'a', profiles, palette: [] } : profiles[1]
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
}

afterEach(cleanup)
beforeEach(() => { calls = []; sessionStorage.clear() })

it('asks only with two profiles or more', () => {
  expect(shouldAskWhoIsPlaying(null)).toBe(false)
  expect(shouldAskWhoIsPlaying({ active: 'a', profiles: [profile('a', 'Player 1')], palette: [], separate_saves: [] })).toBe(false)
  expect(shouldAskWhoIsPlaying({ active: 'a', profiles: [profile('a', 'P1'), profile('b', 'Sam')], palette: [], separate_saves: [] })).toBe(true)
  // "Log in automatically": the box starts as the last profile.
  expect(shouldAskWhoIsPlaying({ active: 'a', auto_login: true, profiles: [profile('a', 'P1'), profile('b', 'Sam')], palette: [], separate_saves: [] })).toBe(false)
})

it('stays away on a box with one profile', async () => {
  serve([profile('a', 'Player 1')])
  const { container } = render(<WhoIsPlaying enabled />)
  await waitFor(() => expect(calls).toHaveLength(1))
  await act(async () => {})
  expect(container.textContent).toBe('')
  expect(useStore.getState().modalDepth).toBe(0)
})

it('waits for the boot, then asks once and switches on a pick', async () => {
  serve([profile('a', 'Player 1'), profile('b', 'Sam')])
  const { rerender, findByText, container } = render(<WhoIsPlaying enabled={false} />)
  expect(calls).toHaveLength(0)
  rerender(<WhoIsPlaying enabled />)
  expect(await findByText('Who’s using this controller?')).toBeTruthy()
  expect(useStore.getState().modalDepth).toBe(1)
  fireEvent.click((await findByText('Sam')).closest('button')!)
  await waitFor(() => expect(calls).toContainEqual(['PUT', '/api/profiles/active']))
  await waitFor(() => expect(container.textContent).toBe(''))
  expect(useStore.getState().modalDepth).toBe(0)

  // A theme switch reloads the page; the question is not asked again.
  const again = render(<WhoIsPlaying enabled />)
  await act(async () => {})
  expect(again.container.textContent).toBe('')
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
  const { findByText } = render(<WhoIsPlaying enabled />)
  fireEvent.click((await findByText('Sam')).closest('button')!)
  expect(await findByText('Close mario.nds before switching profile.')).toBeTruthy()
  expect(await findByText('Who’s using this controller?')).toBeTruthy()
})

it('asks again later when the profiles could not be read at start', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('backend starting') }))
  vi.spyOn(console, 'error').mockImplementation(() => {})
  render(<WhoIsPlaying enabled />)
  await act(async () => {})
  cleanup()
  serve([profile('a', 'Max'), profile('b', 'Sam')])
  const { findByText } = render(<WhoIsPlaying enabled />)
  expect(await findByText('Who’s using this controller?')).toBeTruthy()
})

it('wears the theme’s dress when the theme brings one', async () => {
  const { ThemeProvider } = await import('./ThemeSurface')
  const { buildSdk } = await import('../lib/themeSdk')
  const { createWhoIsPlaying } = await import('../settings/whoIsPlaying')
  const dressed = createWhoIsPlaying(buildSdk('jelly', { selectTheme: async () => {} }), { skin: 'jelly-who' })
  serve([profile('a', 'Max'), profile('b', 'Sam')])
  const { findByText, container } = render(
    <ThemeProvider value={{ whoIsPlaying: dressed } as never}><WhoIsPlaying enabled /></ThemeProvider>)
  await findByText('Who’s using this controller?')
  expect(container.querySelector('.gcs-who.jelly-who')).toBeTruthy()
  expect(container.querySelector('.gcs-skin-default')).toBeNull()
})

it('waits for the theme to load before asking', async () => {
  const { ThemeProvider } = await import('./ThemeSurface')
  serve([profile('a', 'Max'), profile('b', 'Sam')])
  const { container, rerender, findByText } = render(
    <ThemeProvider value={{ loading: true } as never}><WhoIsPlaying enabled /></ThemeProvider>)
  await waitFor(() => expect(calls).toHaveLength(1))
  await act(async () => {})
  expect(container.textContent).toBe('')
  rerender(<ThemeProvider value={{ loading: false } as never}><WhoIsPlaying enabled /></ThemeProvider>)
  expect(await findByText('Who’s using this controller?')).toBeTruthy()
})
