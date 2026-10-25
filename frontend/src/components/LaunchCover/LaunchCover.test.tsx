/**
 * The cover's page: key art when the game has some, the box when it has none,
 * the logo or the name a player says, and a fade on the shell's word.
 */
import { render, screen, cleanup, act, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import LaunchCover, { coverArt, titleOf } from '.'
import { api, type GameMediaIndex } from '../../api'

const index = (media: string[], title = ''): GameMediaIndex => ({
  found: true, available: true, meta: { title },
  media: Object.fromEntries(media.map((t) => [t, { category: 'x', kind: 'image', region: '', cached: true }])),
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  delete (window as unknown as { gamecore?: unknown }).gamecore
})

it('says the name a player says', () => {
  expect(titleOf('Uncharted 2.sh')).toBe('Uncharted 2')
  expect(titleOf('Ico (Europe) (En,Fr,De).iso')).toBe('Ico')
  expect(titleOf('God of War 3')).toBe('God of War 3')
})

it('prefers key art over a title screen, and the scraped title over the file', () => {
  const art = coverArt('rpcs3', 'GoW.iso', index(['screenshot-game-title', 'fanart-background', 'clear-logo'], 'God of War III'))
  expect(art.hero).toContain('/media/fanart-background')
  expect(art.logo).toContain('/media/clear-logo')
  expect(art.title).toBe('God of War III')
})

it('falls back to the box and the name with no media at all', () => {
  const art = coverArt('switch', 'Mario Kart 8.nsp', null)
  expect(art.hero).toBeNull()
  expect(art.logo).toBeNull()
  expect(art.jacket).toBe('/api/covers/switch/Mario%20Kart%208.nsp')
  expect(art.title).toBe('Mario Kart 8')
})

it('fades out when the shell says the game is running', async () => {
  let leave: () => void = () => {}
  ;(window as unknown as { gamecore: unknown }).gamecore = { onCoverLeave: (cb: () => void) => { leave = cb } }
  vi.spyOn(api.media, 'list').mockResolvedValue(index([]))
  window.history.pushState({}, '', '/cover?system=rpcs3&rom=Uncharted%202.sh')
  const { container } = render(<LaunchCover />)
  await waitFor(() => expect(screen.getByText('Uncharted 2')).toBeTruthy())
  const root = container.querySelector('.gc-cover')!
  expect(root.getAttribute('data-leaving')).toBe('0')
  act(() => leave())
  expect(root.getAttribute('data-leaving')).toBe('1')
})
