/**
 * Settings → Profiles: switch, recolour, delete after a confirmation, add
 * through the keyboard. Every theme draws this page.
 */
import { render, waitFor, fireEvent, cleanup } from '@testing-library/react'
import { it, expect, vi, beforeEach, afterEach } from 'vitest'
import { buildSdk } from '../lib/themeSdk'
import { createProfilesPage, savesLine } from '../settings/profiles'
import { createRows } from '../settings/rows'
import { createDialogs } from '../settings/dialog'

let state = {
  active: 'a',
  profiles: [
    { id: 'a', name: 'Max', color: '#b8501b', avatar: null, created: '', primary: true },
    { id: 'b', name: 'Sam', color: '#127a6d', avatar: null, created: '', primary: false },
  ],
  palette: [{ color: '#b8501b', name: 'Ember' }, { color: '#127a6d', name: 'Teal' }],
  separate_saves: ['Nintendo DS'],
  shared_saves: ['PlayStation 3', 'Xbox 360'],
}
let calls: { method: string; url: string; body?: unknown }[] = []

afterEach(cleanup)

const twoProfiles = state
beforeEach(() => {
  calls = []
  state = twoProfiles
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
  expect(container.querySelector('.gcs-row2-badge')?.textContent).toBe('M')
  expect(container.textContent).toContain('Separate saves per profile: Nintendo DS. Other systems share one save.')
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

it('offers no delete on the primary profile', async () => {
  const { findByText, queryByText } = page()
  fireEvent.click(row(await findByText('Max')))
  await findByText('Play as Max')
  expect(queryByText('Delete profile')).toBeNull()
})

it('opens the keyboard to add a profile', async () => {
  const { findByText, getByRole } = page()
  fireEvent.click(row(await findByText('Add profile')))
  expect(getByRole('dialog').textContent).toContain('New profile')
})

it('says every save is shared when no system separates them', () => {
  expect(savesLine([])).toBe('Every system shares one save between profiles.')
  expect(savesLine(undefined)).toBe('Every system shares one save between profiles.')
})

it('names the exceptions when most systems keep saves per profile', () => {
  expect(savesLine(['Nintendo DS', 'PlayStation', 'Wii'], ['Xbox 360']))
    .toBe('Every system keeps separate saves per profile, except Xbox 360.')
  expect(savesLine(['Nintendo DS'], [])).toBe('Every system keeps separate saves per profile.')
})

it('starts profiles by naming the first one, keeping its saves', async () => {
  state = { ...twoProfiles, profiles: [{ ...twoProfiles.profiles[0], name: '' }] }
  const { findByText, queryByText, getByRole, container } = page()
  fireEvent.click(row(await findByText('Set up profiles')))
  expect(container.textContent).toContain('No profiles')
  expect(container.textContent).toContain('keeps the saves already on this console')
  expect(queryByText('Add profile')).toBeNull()
  expect(getByRole('dialog').textContent).toContain('First profile')
})

it('says a deleted profile’s saves are kept but out of reach', async () => {
  const { findByText, container } = page()
  fireEvent.click(row(await findByText('Sam')))
  await findByText('Delete profile')
  expect(container.textContent).toContain('Sam’s saves are kept on the console, but no profile opens them again.')
})
