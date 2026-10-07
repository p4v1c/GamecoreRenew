/**
 * Settings → Profiles: switch, recolour, delete after a confirmation, add
 * through the keyboard. Every theme draws this page.
 */
import { render, waitFor, fireEvent, cleanup, act } from '@testing-library/react'
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
const themes = {
  active: 'shelf',
  themes: [{ id: 'shelf', name: 'Shelf', compatible: true }, { id: 'orbit', name: 'Orbit', compatible: true },
    { id: 'old', name: 'Old', compatible: false }],
}

afterEach(cleanup)

const twoProfiles = state
beforeEach(() => {
  calls = []
  state = twoProfiles
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? 'GET'
    calls.push({ method, url: String(url), body: init?.body && JSON.parse(init.body) })
    const body = String(url).endsWith('/themes') ? themes
      : method === 'GET' ? state : method === 'DELETE' ? { active: 'a' } : state.profiles[1]
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
/** A profile's Edit (or Select) button, in its list row. */
const press = (el: HTMLElement, label: string) =>
  fireEvent.click([...row(el).querySelectorAll('button')].find((b) => b.textContent === label)!)
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
  press(await findByText('Sam'), 'Edit')
  fireEvent.click(row(await findByText('Play as Sam')))
  await waitFor(() => expect(sent('PUT')[0]).toMatchObject({ url: '/api/profiles/active', body: { id: 'b' } }))
  fireEvent.click(container.querySelectorAll('.gcs-val-arrow')[1])
  await waitFor(() => expect(sent('PATCH')[0]).toMatchObject({ url: '/api/profiles/b', body: { color: '#b8501b' } }))
})

it('deletes only after a second press', async () => {
  const { findByText, container } = page()
  press(await findByText('Sam'), 'Edit')
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
  press(await findByText('Max'), 'Edit')
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
  press(await findByText('Sam'), 'Edit')
  await findByText('Delete profile')
  expect(container.textContent).toContain('Sam’s saves are kept on the console, but no profile opens them again.')
})

it('picks a picture for a profile from the grid', async () => {
  const { findByText, getByRole } = page()
  press(await findByText('Sam'), 'Edit')
  fireEvent.click(row(await findByText('Picture')))
  const grid = getByRole('listbox', { name: 'Pictures' })
  expect(grid.querySelectorAll('[role="option"]')).toHaveLength(12)
  fireEvent.click([...grid.querySelectorAll('button')].find((b) => b.textContent === 'Fox')!)
  await waitFor(() => expect(sent('PATCH')[0]).toMatchObject({ url: '/api/profiles/b', body: { avatar: 'fox' } }))
})

it('walks the picture grid in both directions with the pad', async () => {
  const { findByText, getByRole } = page()
  press(await findByText('Sam'), 'Edit')
  fireEvent.click(row(await findByText('Picture')))
  const gp = (name: string) => act(() => { window.dispatchEvent(new CustomEvent(name)) })
  const on = () => getByRole('listbox').querySelector('[data-on="1"] .gcs-pick-label')!.textContent
  expect(on()).toBe('Initial')
  gp('gp:dpad-down'); expect(on()).toBe('Rabbit')    // one row down, same column
  gp('gp:dpad-down'); expect(on()).toBe('Rabbit')    // the last row: stays
  gp('gp:dpad-right'); expect(on()).toBe('Owl')
  gp('gp:back')
  await waitFor(() => expect(() => getByRole('listbox')).toThrow())
  expect(sent('PATCH')).toHaveLength(0)
})

it('gives a profile its own theme, from the ones that load', async () => {
  const { findByText, container } = page()
  press(await findByText('Sam'), 'Edit')
  const theme = row(await findByText('Theme'))
  expect(theme.textContent).toContain('Shelf')
  expect(container.textContent).toContain('Put on when Sam plays.')
  fireEvent.click(theme.querySelectorAll('.gcs-val-arrow')[1])
  await waitFor(() => expect(sent('PATCH')[0]).toMatchObject({ url: '/api/profiles/b', body: { theme: 'orbit' } }))
})

it('opens straight on Profiles from the top bar picture', async () => {
  const { createSettings } = await import('../settings/screen')
  const sdk = buildSdk('shelf', { selectTheme: vi.fn(async () => {}) })
  const Screen = createSettings(sdk, {}, {}) as React.ComponentType<{ onClose: () => void; initialCategory?: string }>
  const { findByText } = render(<Screen onClose={() => {}} initialCategory="profiles" />)
  expect(await findByText(/Who plays on this box/)).toBeTruthy()
})

it('selects another profile from the list, and offers only Edit on the one playing', async () => {
  const { findByText } = page()
  const max = row(await findByText('Max'))
  expect([...max.querySelectorAll('button')].map((b) => b.textContent)).toEqual(['Edit'])
  const sam = row(await findByText('Sam'))
  expect([...sam.querySelectorAll('button')].map((b) => b.textContent)).toEqual(['Select', 'Edit'])
  press(await findByText('Sam'), 'Select')
  await waitFor(() => expect(sent('PUT')[0]).toMatchObject({ url: '/api/profiles/active', body: { id: 'b' } }))
})

it('moves between Select and Edit with the d-pad', async () => {
  const { findByText, container } = page()
  await findByText('Sam')
  window.dispatchEvent(new CustomEvent('gp:dpad-down'))
  await waitFor(() => expect(container.querySelector('.gcs-row2[data-on="1"]')?.textContent).toContain('Sam'))
  window.dispatchEvent(new CustomEvent('gp:dpad-right'))
  await waitFor(() => expect(container.querySelector('.gcs-act[data-pick="1"]')?.textContent).toBe('Edit'))
  window.dispatchEvent(new CustomEvent('gp:confirm'))
  expect(await findByText('Play as Sam')).toBeTruthy()
})

it('turns "Log in automatically" on', async () => {
  const { findByText } = page()
  fireEvent.click(row(await findByText('Log in automatically')))
  await waitFor(() => expect(sent('PUT')[0]).toMatchObject({ url: '/api/profiles/auto-login', body: { enabled: true } }))
})
