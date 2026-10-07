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
import type { ProfilesState } from '../api'

let state: ProfilesState = {
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

const DS4 = { id: '84:30:95:07:c8:1c', name: 'PS4 Controller', connection: 'Bluetooth' }
const XBOX = { id: '045e:0b13', name: 'Xbox Wireless Controller', connection: 'USB' }
let connected = [DS4, XBOX]

afterEach(cleanup)

const twoProfiles = state
beforeEach(() => {
  calls = []
  state = twoProfiles
  connected = [DS4, XBOX]
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? 'GET'
    calls.push({ method, url: String(url), body: init?.body && JSON.parse(init.body) })
    // The backend keeps the pad, so the re-read list shows it.
    if (method === 'POST' && String(url).endsWith('/b/controllers')) {
      const id = JSON.parse(init!.body!).id as string
      state = { ...state, profiles: state.profiles.map((p) => (p.id === 'b'
        ? { ...p, controllers: [...(p.controllers || []), { id, name: id }] } : p)) }
    }
    const body = String(url).endsWith('/themes') ? themes
      : String(url).endsWith('/controllers/pads') ? { pads: connected }
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

// ── controllers shown on a profile ──────────────────────────────────────────

const withPads = () => {
  state = {
    ...twoProfiles,
    profiles: [
      { ...twoProfiles.profiles[0], controllers: [{ id: XBOX.id, name: XBOX.name }] },
      { ...twoProfiles.profiles[1], controllers: [{ id: DS4.id, name: DS4.name }, { id: '0079:0006', name: 'USB Gamepad' }] },
    ],
  }
}

it('lists the profile\'s controllers, connected or not, and removes one', async () => {
  withPads()
  const { findByText, findByRole, getByRole, container } = page()
  press(await findByText('Sam'), 'Edit')
  await detail(findByRole, 'Sam')
  await waitFor(() => expect(container.textContent).toContain('Connected over Bluetooth'))
  expect(container.textContent).toContain('Not connected')
  expect(container.textContent).toContain('2 controllers')
  fireEvent.click(getByRole('button', { name: 'Remove USB Gamepad' }))
  await waitFor(() => expect(sent('DELETE')[0]?.url).toBe('/api/profiles/b/controllers/0079%3A0006'))
})

it('adds a connected pad, saying when another profile shows it', async () => {
  withPads()
  const { findByText, findByRole, getByRole, queryByRole, container } = page()
  press(await findByText('Sam'), 'Edit')
  await detail(findByRole, 'Sam')
  fireEvent.click(getByRole('button', { name: 'Add controller' }))
  const pick = await findByRole('button', { name: 'Add Xbox Wireless Controller' })
  expect(pick.textContent).toContain('Shown on Max')
  expect(queryByRole('button', { name: 'Add PS4 Controller' })).toBeNull()   // already Sam's
  expect(container.textContent).toContain('Pick one to show on Sam')
  fireEvent.click(pick)
  await waitFor(() => expect(sent('POST')[0]).toMatchObject({ url: '/api/profiles/b/controllers', body: { id: XBOX.id } }))
  await waitFor(() => expect(container.querySelector('.gcs-prof [data-on="1"]')!.getAttribute('aria-label')).toBe('Add controller'))
  expect(container.textContent).toContain('Xbox Wireless Controller added to Sam.')
})

it('says so when no other controller is connected', async () => {
  withPads()
  connected = [DS4]
  const { findByText, findByRole, getByRole, container } = page()
  press(await findByText('Sam'), 'Edit')
  await detail(findByRole, 'Sam')
  fireEvent.click(getByRole('button', { name: 'Add controller' }))
  await waitFor(() => expect(container.textContent).toContain('No other controller is connected.'))
  expect(container.querySelector('[data-kind="pick"]')).toBeNull()
})

it('walks down to the controllers, and ○ cancels adding before it leaves', async () => {
  withPads()
  const { findByText, findByRole, container } = page()
  press(await findByText('Sam'), 'Edit')
  await detail(findByRole, 'Sam')
  await waitFor(() => expect(container.textContent).toContain('Connected over Bluetooth'))
  const on = () => container.querySelector('.gcs-prof [data-on="1"]') as HTMLElement
  gp('gp:dpad-down'); gp('gp:dpad-down'); gp('gp:dpad-down'); gp('gp:dpad-down')
  expect(on().getAttribute('aria-label')).toBe('Remove PS4 Controller')
  expect(container.querySelector('.gcs-prof-hint')!.textContent).toContain('Remove')
  gp('gp:dpad-right'); gp('gp:dpad-right'); expect(on().getAttribute('aria-label')).toBe('Add controller')
  gp('gp:confirm')
  await waitFor(() => expect(on().getAttribute('aria-label')).toBe('Add Xbox Wireless Controller'))
  gp('gp:back')
  await waitFor(() => expect(on().getAttribute('aria-label')).toBe('Add controller'))
  gp('gp:confirm')
  await waitFor(() => expect(on().getAttribute('aria-label')).toBe('Add Xbox Wireless Controller'))
  gp('gp:confirm')
  await waitFor(() => expect(container.textContent).toContain('Xbox Wireless Controller added to Sam.'))
  await waitFor(() => expect(on().getAttribute('aria-label')).toBe('Add controller'))
  expect(container.querySelector('.gcs-prof')).not.toBeNull()
  // A third pad wraps "Add controller" to a second row: ↑ climbs row by row.
  gp('gp:dpad-up'); expect(on().getAttribute('aria-label')).toBe('Remove PS4 Controller')
  gp('gp:dpad-up'); expect(on().textContent).toContain('Default')
  gp('gp:dpad-down'); gp('gp:dpad-left')
  expect(on().textContent).toBe('Switch to Sam')
})
