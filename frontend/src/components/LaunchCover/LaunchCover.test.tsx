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

/** jsdom never loads an image: each one waits here until the test lets it. */
const pending: { src: string; done: (ok: boolean) => void }[] = []
class FakeImage {
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  decode = () => Promise.resolve()
  set src(url: string) { pending.push({ src: url, done: (ok) => (ok ? this.onload : this.onerror)?.() }) }
}
const settle = (ok = true) => act(async () => { pending.splice(0).forEach((p) => p.done(ok)) })

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  pending.length = 0
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

it('stays invisible until the key art and the logo are decoded, then shows both at once', async () => {
  vi.stubGlobal('Image', FakeImage)
  vi.spyOn(api.media, 'list').mockResolvedValue(index(['fanart-background', 'clear-logo'], 'God of War III'))
  window.history.pushState({}, '', '/cover?system=rpcs3&rom=GoW.iso')
  const { container } = render(<LaunchCover />)
  const root = container.querySelector('.gc-cover')!
  await waitFor(() => expect(pending.length).toBe(2))
  // Art still loading: no box, no name, nothing drawn yet.
  expect(root.getAttribute('data-shown')).toBe('0')
  expect(container.querySelector('img')).toBeNull()
  expect(screen.queryByText('God of War III')).toBeNull()
  await settle()
  expect(root.getAttribute('data-shown')).toBe('1')
  expect(container.querySelector('.gc-cover-hero')).toBeTruthy()
  expect(container.querySelector('.gc-cover-logo')).toBeTruthy()
  expect(container.querySelector('.gc-cover-jacket')).toBeNull()
})

it('shows the name alone when no image loads', async () => {
  vi.stubGlobal('Image', FakeImage)
  vi.spyOn(api.media, 'list').mockRejectedValue(new Error('offline'))
  window.history.pushState({}, '', '/cover?system=switch&rom=Mario%20Kart%208.nsp')
  const { container } = render(<LaunchCover />)
  await waitFor(() => expect(pending.length).toBe(1))   // the box
  await settle(false)
  expect(container.querySelector('.gc-cover')!.getAttribute('data-shown')).toBe('1')
  expect(container.querySelector('img')).toBeNull()
  expect(screen.getByText('Mario Kart 8')).toBeTruthy()
})

it('fades out when the shell says the game is running', async () => {
  vi.stubGlobal('Image', FakeImage)
  let leave: () => void = () => {}
  ;(window as unknown as { gamecore: unknown }).gamecore = { onCoverLeave: (cb: () => void) => { leave = cb } }
  vi.spyOn(api.media, 'list').mockResolvedValue(index([]))
  window.history.pushState({}, '', '/cover?system=rpcs3&rom=Uncharted%202.sh')
  const { container } = render(<LaunchCover />)
  await waitFor(() => expect(pending.length).toBe(1))
  await settle()
  expect(screen.getByText('Uncharted 2')).toBeTruthy()
  const root = container.querySelector('.gc-cover')!
  expect(root.getAttribute('data-leaving')).toBe('0')
  act(() => leave())
  expect(root.getAttribute('data-leaving')).toBe('1')
})
