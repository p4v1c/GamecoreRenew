/**
 * Settings → Profiles: switch, recolour, delete after a confirmation, add
 * through the keyboard. Every theme draws this page.
 */
import { render, waitFor, fireEvent, cleanup } from '@testing-library/react'
import { it, expect, vi, beforeEach, afterEach } from 'vitest'
import { buildSdk } from '../lib/themeSdk'
import { createProfilesPage } from '../settings/profiles'
import { createRows } from '../settings/rows'
import { createDialogs } from '../settings/dialog'

const state = {
  active: 'a',
  profiles: [
    { id: 'a', name: 'Player 1', color: '#b8501b', avatar: null, created: '', primary: true },
    { id: 'b', name: 'Sam', color: '#127a6d', avatar: null, created: '', primary: false },
  ],
  palette: [{ color: '#b8501b', name: 'Ember' }, { color: '#127a6d', name: 'Teal' }],
}
let calls: { method: string; url: string; body?: unknown }[] = []

afterEach(cleanup)

beforeEach(() => {
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? 'GET'
    calls.push({ method, url: String(url), body: init?.body && JSON.parse(init.body) })
    const body = method === 'GET' ? state : method === 'DELETE' ? { active: 'a' } : state.profiles[1]
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
})

const page = () => {
  const sdk = buildSdk('shelf', { selectTheme: vi.fn(async () => {}) })
  const Page = createProfilesPage(sdk, createRows(sdk), createDialogs(sdk).Dialog) as
    React.ComponentType<{ active: boolean; onLeave: () => void }>
  return render(<Page active onLeave={() => {}} />)
}
const row = (el: HTMLElement) => el.closest('.gcs-row2') as HTMLElement
const sent = (method: string) => calls.filter((c) => c.method === method)

it('lists the profiles with the one playing now', async () => {
  const { findByText, container } = page()
  await findByText('Sam')
  expect(container.textContent).toContain('Playing now')
  expect(container.textContent).toContain('2 profiles')
  expect(container.querySelector('.gcs-row2-badge')?.textContent).toBe('P')
})

it('switches to a profile and changes its colour', async () => {
  const { findByText, container } = page()
  fireEvent.click(row(await findByText('Sam')))
  fireEvent.click(row(await findByText('Play as Sam')))
  await waitFor(() => expect(sent('PUT')[0]).toMatchObject({ url: '/api/profiles/active', body: { id: 'b' } }))
  fireEvent.click(container.querySelectorAll('.gcs-val-arrow')[1])
  await waitFor(() => expect(sent('PATCH')[0]).toMatchObject({ url: '/api/profiles/b', body: { color: '#b8501b' } }))
})

it('deletes only after a second press', async () => {
  const { findByText, container } = page()
  fireEvent.click(row(await findByText('Sam')))
  const del = row(await findByText('Delete profile'))
  expect(del.dataset.danger).toBe('1')
  fireEvent.click(del)
  expect(sent('DELETE')).toHaveLength(0)
  fireEvent.click(del)
  await waitFor(() => expect(sent('DELETE')[0]?.url).toBe('/api/profiles/b'))
  await waitFor(() => expect(container.textContent).toContain('Sam deleted.'))
})

it('opens the keyboard to add a profile', async () => {
  const { findByText, getByRole } = page()
  fireEvent.click(row(await findByText('Add profile')))
  expect(getByRole('dialog').textContent).toContain('New profile')
})
