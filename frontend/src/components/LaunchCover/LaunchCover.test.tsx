/**
 * The cover's page: key art when the game has some, the box when it has none,
 * no name and no plate, and a fade on the shell's word.
 */
import { render, screen, cleanup, act, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import LaunchCover, { coverArt } from '.'
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

it('prefers key art over a title screen', () => {
  const art = coverArt('rpcs3', 'GoW.iso', index(['screenshot-game-title', 'fanart-background', 'clear-logo']))
  expect(art.hero).toContain('/media/fanart-background')
})

it('falls back to the box with no media at all', () => {
  const art = coverArt('switch', 'Mario Kart 8.nsp', null)
  expect(art.hero).toBeNull()
  expect(art.jacket).toBe('/api/covers/switch/Mario%20Kart%208.nsp')
})

it('stays invisible until the key art is decoded, then shows it with no name or plate', async () => {
  vi.stubGlobal('Image', FakeImage)
  vi.spyOn(api.media, 'list').mockResolvedValue(index(['fanart-background', 'clear-logo'], 'God of War III'))
  window.history.pushState({}, '', '/cover?system=rpcs3&rom=GoW.iso')
  const { container } = render(<LaunchCover />)
  const root = container.querySelector('.gc-cover')!
  await waitFor(() => expect(pending.length).toBe(1))
  // Art still loading: nothing drawn yet.
  expect(root.getAttribute('data-shown')).toBe('0')
  expect(container.querySelector('img')).toBeNull()
  expect(screen.queryByText('God of War III')).toBeNull()
  await settle()
  expect(root.getAttribute('data-shown')).toBe('1')
  expect(container.querySelector('.gc-cover-hero')).toBeTruthy()
  expect(container.querySelector('.gc-cover-jacket')).toBeNull()
  expect(screen.queryByText('God of War III')).toBeNull()
  expect(container.querySelector('.gc-cover-name, .gc-cover-logo, .gc-cover-title')).toBeNull()
})

it('shows the ground and the ring alone when no image loads', async () => {
  vi.stubGlobal('Image', FakeImage)
  vi.spyOn(api.media, 'list').mockRejectedValue(new Error('offline'))
  window.history.pushState({}, '', '/cover?system=switch&rom=Mario%20Kart%208.nsp')
  const { container } = render(<LaunchCover />)
  await waitFor(() => expect(pending.length).toBe(1))   // the box
  await settle(false)
  expect(container.querySelector('.gc-cover')!.getAttribute('data-shown')).toBe('1')
  expect(container.querySelector('img')).toBeNull()
  expect(screen.getByRole('progressbar')).toBeTruthy()
  expect(screen.queryByText('Mario Kart 8')).toBeNull()
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
  const root = container.querySelector('.gc-cover')!
  expect(root.getAttribute('data-leaving')).toBe('0')
  act(() => leave())
  expect(root.getAttribute('data-leaving')).toBe('1')
})

it('is reused: a game by message, the next game by message, blank in between', async () => {
  vi.stubGlobal('Image', FakeImage)
  const on: Record<string, (d?: unknown) => void> = {}
  const off = vi.fn()
  ;(window as unknown as { gamecore: unknown }).gamecore = {
    onCoverGame: (cb: (d: unknown) => void) => { on.game = cb; return off },
    onCoverLeave: (cb: () => void) => { on.leave = cb; return off },
    onCoverReset: (cb: () => void) => { on.reset = cb; return off },
  }
  vi.spyOn(api.media, 'list').mockResolvedValue(index([]))
  window.history.pushState({}, '', '/cover')
  const { container, unmount } = render(<LaunchCover />)
  const root = container.querySelector('.gc-cover')!
  expect(root.getAttribute('data-shown')).toBe('0')   // warmed, no game yet

  act(() => on.game({ system: 'rpcs3', rom: 'God of war 3' }))
  await waitFor(() => expect(pending.length).toBe(1))
  await settle()
  expect(container.querySelector('.gc-cover-jacket')!.getAttribute('src')).toContain('God%20of%20war%203')
  act(() => on.leave())
  expect(root.getAttribute('data-leaving')).toBe('1')

  act(() => on.reset())
  expect(root.getAttribute('data-shown')).toBe('0')
  expect(root.getAttribute('data-leaving')).toBe('0')
  expect(container.querySelector('img')).toBeNull()

  act(() => on.game({ system: 'switch', rom: 'Cuphead.nsp' }))
  await waitFor(() => expect(pending.length).toBe(1))
  await settle()
  expect(container.querySelector('.gc-cover-jacket')!.getAttribute('src')).toContain('Cuphead.nsp')
  unmount()
  expect(off).toHaveBeenCalledTimes(3)
})
