import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createElement } from 'react'
import { buildSdk } from './themeSdk'
import { useStore } from '../store'

const systems = [
  { id: 'rpcs3', label: 'RPCS3', kind: 'emulator', iconPath: 'rpcs3.svg' },
  { id: 'youtube', label: 'YouTube', kind: 'app', iconPath: 'youtube.svg' },
  { id: 'pcsx2', label: 'PCSX2', kind: 'emulator', iconPath: 'pcsx2.svg' },
]
const games = [
  { filename: 'Flower.iso', display_name: 'Flower', path: '/test/Flower.iso' },
  { filename: 'Journey.iso', display_name: 'Journey', path: '/test/Journey.iso' },
]
const playtime = [{ system_id: 'rpcs3', game_key: 'Journey.iso', total_secs: 7200,
  session_count: 1, last_played: '2026-09-01T20:00:00Z' }]
let emptyHistory = false

beforeEach(() => {
  emptyHistory = false
  useStore.setState({ screen: 'home', selectedSystemId: null, selectedGameIdx: 0,
    gridFocusIdx: 0, gridPage: 0, modalDepth: 0, standby: 'off', powerPending: null,
    sessionGameKey: null, sessionSystemId: null, backgroundSessions: [] })
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.endsWith('/systems') ? systems
      : url.endsWith('/systems/rpcs3') ? systems[0]
      : url.endsWith('/systems/rpcs3/games') ? games
      : url.endsWith('/systems/pcsx2') ? systems[2]
      : url.endsWith('/systems/pcsx2/games') ? [{ filename: 'Journey.iso', display_name: 'Another journey', path: '/test/ps2/Journey.iso' }]
      : url.includes('/playtime') ? emptyHistory ? [] : playtime
      : url.includes('/metadata/') ? { found: true, title: 'Journey', description: 'Across the dunes.', genres: ['Adventure'], year: '2012' }
      : url.includes('/media/') ? { media: { 'fanart-background': { kind: 'image' } } }
      : url.endsWith('/sysinfo') ? { controllers: [], ip: '192.0.2.1' }
      : url.includes('/settings') ? {}
      : { ok: true }
    return { ok: true, status: 200, json: async () => body }
  }))
})

it('offers All and keeps identically named ROMs from different consoles distinct', async () => {
  const r = await mountOrbit()
  await act(async () => { fireEvent.click(r.getByText('Library', { selector: '.nav-item' })) })
  await act(async () => { fireEvent.click(r.getByRole('button', { name: 'All' })) })
  await waitFor(() => expect(r.container.querySelectorAll('.library-card')).toHaveLength(3))
  await act(async () => { fireEvent.click(r.getByText('Another journey', { selector: '.library-card h3' })) })
  await act(async () => { fireEvent.click(r.getByText('▶ Play')) })
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/games/launch', expect.objectContaining({
    body: JSON.stringify({ system_id: 'pcsx2', rom_path: '/test/ps2/Journey.iso', game_key: 'Journey.iso' }),
  })))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

async function mountOrbit() {
  const path = '../../../config/themes/orbit/index.js'
  const { default: createOrbit } = await import(/* @vite-ignore */ path)
  const sdk = buildSdk('orbit', { selectTheme: vi.fn(async () => {}) })
  const theme = createOrbit(sdk)
  const result = render(createElement(theme.shell))
  await waitFor(() => expect(result.container.querySelector('.tile-label')?.textContent).toBe('Journey'))
  return result
}

it('opens the complete library while its system is still loading', async () => {
  const r = await mountOrbit()
  await act(async () => { fireEvent.click(r.getByText('Library', { selector: '.nav-item' })) })
  await waitFor(() => expect(r.container.querySelectorAll('.library-card')).toHaveLength(2))
  expect(r.container.querySelector('#library-title')?.textContent).toBe('Your library.')
})

it('keeps the Applications view mounted when moving there from Library', async () => {
  const r = await mountOrbit()
  await act(async () => { fireEvent.click(r.getByText('Applications', { selector: '.nav-item' })) })
  expect(r.container.querySelector('#applications-view')).toBeTruthy()
  await act(async () => { fireEvent.click(r.getByText('Library', { selector: '.nav-item' })) })
  await act(async () => { fireEvent.click(r.getByText('Applications', { selector: '.nav-item' })) })
  expect(r.container.querySelector('#applications-view')).toBeTruthy()
})

it('uses the selected game artwork and the mockup hero and selection styles', async () => {
  const r = await mountOrbit()
  await waitFor(() => expect(r.container.querySelector('.backdrop img')?.getAttribute('src'))
    .toBe('/api/media/rpcs3/Journey.iso/media/fanart-background'))
  expect(r.container.querySelector('#hero-title')?.textContent).toBe('Journey')
  expect(r.container.querySelector('.game-tile.selected .tile-label')?.textContent).toBe('Journey')
  expect(r.getByRole('button', { name: 'Game details' })).toBeTruthy()
})

it('puts a miniature jacket inside the square game tile instead of a disc', async () => {
  const r = await mountOrbit()
  const cover = r.container.querySelector('.home-game-tile.selected .home-game-cover img')
  expect(cover?.getAttribute('src')).toBe('/api/covers/rpcs3/Journey.iso')
  expect(r.container.querySelector('.orbit-disc')).toBeNull()
})

it('fills the library with full 2:3 jackets', async () => {
  const r = await mountOrbit()
  await act(async () => { fireEvent.click(r.getByText('Library', { selector: '.nav-item' })) })
  await waitFor(() => expect(r.container.querySelectorAll('.library-card')).toHaveLength(2))
  expect(r.container.querySelectorAll('.library-cover > img')).toHaveLength(2)
  expect(r.container.querySelector('.library-grid .orbit-physical')).toBeNull()
})

it('shows installed games even before any have been played', async () => {
  emptyHistory = true
  const path = '../../../config/themes/orbit/index.js'
  const { default: createOrbit } = await import(/* @vite-ignore */ path)
  const r = render(createElement(createOrbit(buildSdk('orbit', { selectTheme: vi.fn() })).shell))
  await waitFor(() => expect([...r.container.querySelectorAll('.tile-label')].map(e => e.textContent)).toContain('Flower'))
})

it('Play on a recent game launches that ROM, not the first game in its console', async () => {
  const r = await mountOrbit()
  await act(async () => { fireEvent.click(r.getByText('Play', { selector: '.primary-button' })) })
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/games/launch', expect.objectContaining({
    body: JSON.stringify({ system_id: 'rpcs3', rom_path: '/test/Journey.iso', game_key: 'Journey.iso' }),
  })))
})

it('opens the search keyboard from its visible button', async () => {
  const r = await mountOrbit()
  await act(async () => { fireEvent.click(r.getByText('Library', { selector: '.nav-item' })) })
  await act(async () => { fireEvent.click(r.getByRole('button', { name: 'Open the search keyboard' })) })
  expect(r.getByText('Search games')).toBeTruthy()
})

it('sorts with the visible buttons and changes tabs with R1 from Library', async () => {
  const r = await mountOrbit()
  await act(async () => { fireEvent.click(r.getByText('Library', { selector: '.nav-item' })) })
  await waitFor(() => expect(r.container.querySelectorAll('.library-card')).toHaveLength(2))
  await act(async () => { fireEvent.click(r.getByText('Recent', { selector: '.library-sort button' })) })
  expect(r.container.querySelector('.library-card h3')?.textContent).toBe('Journey')
  await act(async () => { window.dispatchEvent(new CustomEvent('gp:r1')) })
  expect(r.container.querySelector('#applications-view')).toBeTruthy()
})

it('opens only a visible favourite with the pad and restores focus after details', async () => {
  const path = '../../../config/themes/orbit/lib/catalog.js'
  const catalog = await import(/* @vite-ignore */ path)
  if (!catalog.isFavourite('rpcs3', 'Journey.iso')) catalog.toggleFavourite('rpcs3', 'Journey.iso')
  const r = await mountOrbit()
  await act(async () => { fireEvent.click(r.getByText('Library', { selector: '.nav-item' })) })
  await waitFor(() => expect(r.container.querySelectorAll('.library-card')).toHaveLength(2))
  await act(async () => { fireEvent.click(r.getByText('Favourites', { selector: 'button' })) })
  await act(async () => { window.dispatchEvent(new CustomEvent('gp:confirm')) })
  expect(r.getByRole('dialog', { name: 'Journey' })).toBeTruthy()
  expect(fetch).not.toHaveBeenCalledWith('/api/games/launch', expect.anything())
  await act(async () => { window.dispatchEvent(new CustomEvent('gp:back')) })
  expect(r.queryByRole('dialog')).toBeNull()
  expect(useStore.getState().modalDepth).toBe(0)
  catalog.toggleFavourite('rpcs3', 'Journey.iso')
})
