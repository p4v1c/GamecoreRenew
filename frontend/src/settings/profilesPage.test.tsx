/**
 * Settings → Profiles: the cards, one profile's page (picture, colour, theme,
 * delete after a confirmation), the keyboard to add one. Every theme draws
 * this page.
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
const card = (el: HTMLElement) => el.closest('.gcs-pcard') as HTMLElement
const labels = (el: HTMLElement) => [...card(el).querySelectorAll('button')].map((b) => b.textContent!.trim())
const press = (el: HTMLElement, label: string) =>
  fireEvent.click([...card(el).querySelectorAll('button')].find((b) => b.textContent!.trim() === label)!)
const sent = (method: string) => calls.filter((c) => c.method === method)
const gp = (name: string) => act(() => { window.dispatchEvent(new CustomEvent(name)) })
/** The profile page over the screen, once it is up. */
const detail = async (findByRole: (r: string, o: object) => Promise<HTMLElement>, name: string) =>
  findByRole('dialog', { name })

it('shows a card per profile, the one playing marked', async () => {
  const { findByText, container } = page()
  await findByText('Sam')
  expect(container.textContent).toContain('Playing now')
  expect(container.textContent).toContain('2 profiles')
  expect(container.querySelector('.gcs-pcard-face')?.textContent).toBe('M')
  expect(container.textContent).toContain('Separate saves per profile: Nintendo DS. Other systems share one save.')
})

it('switches from the list, and offers only Edit on the one playing', async () => {
  const { findByText } = page()
  expect(labels(await findByText('Max'))).toEqual(['Edit'])
  expect(labels(await findByText('Sam'))).toEqual(['Switch', 'Edit'])
  press(await findByText('Sam'), 'Switch')
  await waitFor(() => expect(sent('PUT')[0]).toMatchObject({ url: '/api/profiles/active', body: { id: 'b' } }))
})

it('walks the cards with the d-pad, down to the row and back', async () => {
  const { findByText, findByRole, container } = page()
  await findByText('Sam')
  const on = () => container.querySelector('.gcs-pcard-btn[data-on="1"]')
  expect(on()?.textContent?.trim()).toBe('Edit')                 // Max's
  gp('gp:dpad-right'); expect(on()?.textContent?.trim()).toBe('Switch')
  gp('gp:dpad-down')
  expect(container.querySelector('.gcs-row2[data-on="1"]')?.textContent).toContain('Log in automatically')
  gp('gp:dpad-up'); gp('gp:dpad-right')
  expect(on()?.textContent?.trim()).toBe('Edit')
  gp('gp:confirm')
  expect(await detail(findByRole, 'Sam')).toBeTruthy()
})

it('changes the picture, the colour and the theme on the profile page', async () => {
  const { findByText, findByRole, getByRole, container } = page()
  press(await findByText('Sam'), 'Edit')
  await detail(findByRole, 'Sam')
  expect(container.textContent).toContain('Put on when Sam plays')
  fireEvent.click(getByRole('button', { name: 'Fox' }))
  fireEvent.click(getByRole('button', { name: 'Ember' }))
  fireEvent.click([...container.querySelectorAll('.gcs-prof-theme')].find((b) => b.textContent!.includes('Orbit'))!)
  await waitFor(() => expect(sent('PATCH').map((c) => c.body)).toEqual([{ avatar: 'fox' }, { color: '#b8501b' }, { theme: 'orbit' }]))
  expect(container.querySelectorAll('.gcs-prof-theme')).toHaveLength(3)   // Default, Shelf, Orbit: not Old
})

it('moves through the page in two directions with the pad', async () => {
  const { findByText, findByRole, container } = page()
  press(await findByText('Sam'), 'Edit')
  await detail(findByRole, 'Sam')
  const on = () => container.querySelector('.gcs-prof [data-on="1"]') as HTMLElement
  expect(on().getAttribute('aria-label')).toBe('Initial')
  gp('gp:dpad-down'); expect(on().getAttribute('aria-label')).toBe('Rabbit')
  gp('gp:dpad-down'); expect(on().getAttribute('aria-label')).toBe('Ember')
  gp('gp:dpad-down'); expect(on().textContent).toContain('Default')
  gp('gp:dpad-left'); expect(on().textContent).toBe('Switch to Sam')
  gp('gp:back')
  await waitFor(() => expect(container.querySelector('.gcs-prof')).toBeNull())
})

it('deletes only after a second press, and says where the saves went', async () => {
  const { findByText, findByRole, getByRole, container } = page()
  press(await findByText('Sam'), 'Edit')
  await detail(findByRole, 'Sam')
  expect(container.textContent).toContain('Sam’s saves are kept on the console, but no profile opens them again.')
  fireEvent.click(getByRole('button', { name: 'Delete Sam' }))
  expect(sent('DELETE')).toHaveLength(0)
  fireEvent.click(getByRole('button', { name: 'Press again to delete Sam' }))
  await waitFor(() => expect(sent('DELETE')[0]?.url).toBe('/api/profiles/b'))
  await waitFor(() => expect(container.textContent).toContain('Sam deleted.'))
})

it('offers no delete on the primary profile', async () => {
  const { findByText, findByRole, queryByRole, container } = page()
  press(await findByText('Max'), 'Edit')
  await detail(findByRole, 'Max')
  expect(queryByRole('button', { name: /Delete/ })).toBeNull()
  expect(queryByRole('button', { name: /Switch to/ })).toBeNull()
  expect(container.textContent).toContain('Keeps the saves made before profiles')
})

it('opens the keyboard to add a profile', async () => {
  const { findByText, getByRole } = page()
  fireEvent.click(await findByText('Add profile'))
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
  fireEvent.click((await findByText('Set up profiles')).closest('.gcs-row2')!)
  expect(container.textContent).toContain('No profiles')
  expect(container.textContent).toContain('keeps the saves already on this console')
  expect(queryByText('Add profile')).toBeNull()
  expect(getByRole('dialog').textContent).toContain('First profile')
})

it('opens straight on Profiles from the top bar picture', async () => {
  const { createSettings } = await import('../settings/screen')
  const sdk = buildSdk('shelf', { selectTheme: vi.fn(async () => {}) })
  const Screen = createSettings(sdk, {}, {}) as React.ComponentType<{ onClose: () => void; initialCategory?: string }>
  const { findByText } = render(<Screen onClose={() => {}} initialCategory="profiles" />)
  expect(await findByText(/Who plays on this box/)).toBeTruthy()
})

it('turns "Log in automatically" on', async () => {
  const { findByText } = page()
  fireEvent.click((await findByText('Log in automatically')).closest('.gcs-row2')!)
  await waitFor(() => expect(sent('PUT')[0]).toMatchObject({ url: '/api/profiles/auto-login', body: { enabled: true } }))
})
