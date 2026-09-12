import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createElement } from 'react'
import { buildSdk } from './themeSdk'
import { useStore } from '../store'

/**
 * The shape of a shelf, and why it is measured once.
 *
 * Every library cell reserved a 2:3 portrait. That is a Switch case exactly and
 * nothing else: a Game Boy box is nearly square and a Nintendo 64 carton is
 * landscape, so each row carried a band of empty space as tall as the
 * difference. 3.6.19 made the frame hug the picture, which fixed the border and
 * left the band — which is what the photograph of a Game Boy shelf showed.
 *
 * Letting each card size itself is the thing the fixed cell was there to
 * prevent: "changing every card's grid geometry as hundreds of cached images
 * decode stalls pad navigation on larger libraries." What breaks the deadlock is
 * that a console's boxes are all one shape and a library view is one console, so
 * one ratio describes the whole grid. The wall relayouts once and never again,
 * and THAT is what is asserted here — the ratio reaching the grid is easy, the
 * "never again" is the part that would regress silently.
 *
 * jsdom decodes nothing, so `naturalWidth`/`naturalHeight` are 0 and the load
 * handler would bail before measuring. They are defined per element below,
 * which is the only way this path is reachable in a test at all.
 */
const systems = [
  { id: 'rpcs3', label: 'RPCS3', kind: 'emulator', iconPath: 'rpcs3.svg' },
  { id: 'pcsx2', label: 'PCSX2', kind: 'emulator', iconPath: 'pcsx2.svg' },
]
const games = [
  { filename: 'Flower.iso', display_name: 'Flower', path: '/test/Flower.iso' },
  { filename: 'Journey.iso', display_name: 'Journey', path: '/test/Journey.iso' },
]

beforeEach(() => {
  useStore.setState({ screen: 'home', selectedSystemId: null, selectedGameIdx: 0,
    gridFocusIdx: 0, gridPage: 0, modalDepth: 0, standby: 'off', powerPending: null,
    sessionGameKey: null, sessionSystemId: null, backgroundSessions: [], transition: null })
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.endsWith('/systems') ? systems
      : url.endsWith('/systems/rpcs3') ? systems[0]
      : url.endsWith('/systems/rpcs3/games') ? games
      : url.endsWith('/systems/pcsx2') ? systems[1]
      : url.endsWith('/systems/pcsx2/games') ? [{ filename: 'Ico.iso', display_name: 'Ico', path: '/test/ps2/Ico.iso' }]
      : url.includes('/playtime') ? []
      : url.includes('/metadata/') ? { found: false }
      : url.includes('/media/') ? { media: {} }
      : url.endsWith('/sysinfo') ? { controllers: [], ip: '192.0.2.1' }
      : url.includes('/settings') ? {}
      : { ok: true }
    return { ok: true, status: 200, json: async () => body }
  }))
})

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

async function openLibrary() {
  const path = '../../../config/themes/orbit/index.js'
  const { default: createOrbit } = await import(/* @vite-ignore */ path)
  const r = render(createElement(createOrbit(buildSdk('orbit', { selectTheme: vi.fn() })).shell))
  await waitFor(() => expect(r.container.querySelector('.tile-label')).toBeTruthy())
  await act(async () => { fireEvent.click(r.getByText('Consoles', { selector: '.nav-item' })) })
  await act(async () => { fireEvent.click(r.getByRole('button', { name: /Browse games/ })) })
  await waitFor(() => expect(r.container.querySelectorAll('.library-jacket > img').length).toBe(2))
  return r
}

/** Report a decoded size for one picture, the way a browser would. */
async function decode(img: Element, width: number, height: number) {
  Object.defineProperty(img, 'naturalWidth', { value: width, configurable: true })
  Object.defineProperty(img, 'naturalHeight', { value: height, configurable: true })
  await act(async () => { fireEvent.load(img) })
}

const shelfRatio = (r: ReturnType<typeof render>) =>
  (r.container.querySelector('.library-grid') as HTMLElement | null)
    ?.style.getPropertyValue('--jacket-ratio')

it('reserves nothing until a picture has said what shape this console is', async () => {
  // Before any measurement the grid says nothing and the stylesheet's own 2:3
  // fallback stands. A grid that guessed early would move twice.
  const r = await openLibrary()
  expect(shelfRatio(r)).toBe('')
})

it('gives the whole shelf the shape of its console', async () => {
  const r = await openLibrary()
  const [first] = r.container.querySelectorAll('.library-jacket > img')
  await decode(first, 640, 700)          // a near-square Game Boy box
  await waitFor(() => expect(shelfRatio(r)).toBe(String(640 / 700)))
})

it('does not move the wall again when the next jacket decodes', async () => {
  // The regression that would not be noticed: scraped covers for one console
  // differ by a few pixels, and taking the latest would shift every row under
  // the player's thumb each time one arrived.
  const r = await openLibrary()
  const imgs = [...r.container.querySelectorAll('.library-jacket > img')]
  await decode(imgs[0], 640, 700)
  await waitFor(() => expect(shelfRatio(r)).toBe(String(640 / 700)))
  await decode(imgs[1], 600, 900)
  expect(shelfRatio(r)).toBe(String(640 / 700))
})

it('ignores a banner rather than shaping the shelf like one', async () => {
  // `plausible()` rejects anything wider than 1.5 — FIFA 19's 320x176 EA
  // banner is the one that taught it. A rejected picture must not be allowed
  // to describe the console either.
  const r = await openLibrary()
  const [first] = r.container.querySelectorAll('.library-jacket > img')
  await decode(first, 320, 176)
  expect(shelfRatio(r)).toBe('')
})

it('measures again when the player moves to another console', async () => {
  const r = await openLibrary()
  const [first] = r.container.querySelectorAll('.library-jacket > img')
  await decode(first, 640, 700)
  await waitFor(() => expect(shelfRatio(r)).toBe(String(640 / 700)))
  await act(async () => { fireEvent.click(r.getByRole('button', { name: 'PS2' })) })
  await waitFor(() => expect(shelfRatio(r)).toBe(''))
})

it('leaves the All shelf on the fallback, having no single shape to take', async () => {
  const r = await openLibrary()
  await act(async () => { fireEvent.click(r.getByRole('button', { name: 'All' })) })
  await waitFor(() => expect(r.container.querySelectorAll('.library-jacket > img').length)
    .toBeGreaterThan(0))
  const [first] = r.container.querySelectorAll('.library-jacket > img')
  await decode(first, 640, 700)
  expect(shelfRatio(r)).toBe('')
})
