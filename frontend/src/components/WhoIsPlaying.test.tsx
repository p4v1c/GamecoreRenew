/**
 * "Who's playing?" appears only with two profiles or more, once per start,
 * and a pick switches the active profile.
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
  expect(shouldAskWhoIsPlaying({ active: 'a', profiles: [profile('a', 'Player 1')], palette: [] })).toBe(false)
  expect(shouldAskWhoIsPlaying({ active: 'a', profiles: [profile('a', 'P1'), profile('b', 'Sam')], palette: [] })).toBe(true)
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
  expect(await findByText('Who’s playing?')).toBeTruthy()
  expect(useStore.getState().modalDepth).toBe(1)
  fireEvent.click((await findByText('Sam')).closest('button')!)
  await waitFor(() => expect(calls).toContainEqual(['PUT', '/api/profiles/active']))
  expect(container.textContent).toBe('')
  expect(useStore.getState().modalDepth).toBe(0)

  // A theme switch reloads the page; the question is not asked again.
  const again = render(<WhoIsPlaying enabled />)
  await act(async () => {})
  expect(again.container.textContent).toBe('')
})
