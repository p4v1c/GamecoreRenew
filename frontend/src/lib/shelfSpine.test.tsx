/**
 * Which way round Shelf lays a spine scan.
 *
 * ScreenScraper's `box-2D-side` is whichever face carries the title on a
 * shelf, and which face that IS depends on the shape of the box. A PS1, DS or
 * Switch box is portrait and its side is the tall left face; an N64 box is
 * landscape and its printed side is the wide top band. Measured on the
 * reference box: every one of the eight N64 titles came back around 680x115,
 * against 42x680 for a Switch one — a ratio of 6.2 against 0.06.
 *
 * Shelf stands every game upright, and both faces a spine can go on are tall
 * and narrow. A band dropped in unturned is scaled by `object-fit: cover`
 * until it covers 320px of HEIGHT, and 34px of a 1891px picture is kept — 1.8
 * % of it, from the horizontal centre, which on an N64 jacket is the gap
 * between the logo and the publisher's mark. Five of the eight came out under
 * 10/255 of luminance; Mario Kart 64 at 9. Nothing was missing and nothing had
 * failed: the scans are on disk, complete and correct.
 *
 * jsdom decodes no images, so `naturalWidth` is supplied here the same way
 * `clientWidth` is supplied in shelfLibrary.test.tsx — the layout numbers this
 * environment cannot produce are the ones the assertion is about.
 */
import { render, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React, { createElement } from 'react'
import { buildSdk } from './themeSdk'
import { useStore } from '../store'
import LibraryScreen from '../components/LibraryScreen'

const THEME = '../../../config/themes/shelf'

const GAMES = [
  { filename: 'mario-kart-64.z64', display_name: 'Mario Kart 64',
    path: '/roms/mario-kart-64.z64', ext: '.z64' },
  { filename: 'super-mario-64.z64', display_name: 'Super Mario 64',
    path: '/roms/super-mario-64.z64', ext: '.z64' },
]

beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() { return (this as HTMLElement).classList.contains('cz-stage') ? 1434 : 0 },
  })
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(typeof input === 'string' ? input : (input as Request).url ?? input)
    const body: unknown = url.includes('/games') ? GAMES
      : url.includes('/systems/') ? { id: 'gopher64', label: 'Nintendo 64', color: '#b400ff' }
        : []
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
  useStore.setState({
    screen: 'library', selectedSystemId: 'gopher64', selectedGameIdx: 0,
    modalDepth: 0, sessionGameKey: null,
  })
})

afterEach(async () => {
  const { cleanup } = await import('@testing-library/react')
  cleanup()
  vi.unstubAllGlobals()
  Reflect.deleteProperty(HTMLElement.prototype, 'clientWidth')
})

async function shelf() {
  const sdk = buildSdk('shelf', { selectTheme: vi.fn(async () => {}) })
  const load = (p: string) => import(/* @vite-ignore */ p)
  const [lib, accent, browse, dossier, box, cart] = await Promise.all([
    load(`${THEME}/views/library.js`),
    load(`${THEME}/lib/accent.js`),
    load(`${THEME}/lib/browse.js`),
    load(`${THEME}/lib/dossier.js`),
    load(`${THEME}/views/box.js`),
    load(`${THEME}/views/cartridge.js`),
  ])
  const View = lib.createLibraryView(sdk, {
    accent: accent.createAccentStore(sdk),
    useBrowse: browse.createUseBrowse(sdk),
    useDossier: dossier.createUseDossier(sdk),
    Box: box.createBox(sdk),
    Cartridge: cart.createCartridge(sdk),
  })
  const r = render(createElement(
    LibraryScreen as React.ComponentType<{ view: unknown; omit: string[] }>,
    { view: View, omit: ['options'] }))
  await act(async () => { await new Promise(res => setTimeout(res, 0)) })
  return r
}

/** Say what a decoded image would have measured, then let it load. */
const loadsAs = async (img: HTMLImageElement, w: number, h: number) => {
  Object.defineProperty(img, 'naturalWidth', { configurable: true, get: () => w })
  Object.defineProperty(img, 'naturalHeight', { configurable: true, get: () => h })
  await act(async () => { img.dispatchEvent(new Event('load')) })
}

const spines = (c: HTMLElement) =>
  [...c.querySelectorAll<HTMLImageElement>('.cz-spine > img')]

describe('Shelf — a spine scan is stood upright, whichever way it was printed', () => {
  it('turns a landscape band a quarter turn', async () => {
    // The N64 case. Left flat, `cover` keeps 1.8 % of this picture.
    const { container } = await shelf()
    const img = spines(container)[0]
    expect(img).toBeTruthy()
    await loadsAs(img, 680, 115)
    expect(img.dataset.wide).toBe('1')
  })

  it('leaves a portrait scan alone', async () => {
    // Every other system on the box. Turning this one would BE the defect,
    // with the sign flipped.
    const { container } = await shelf()
    const img = spines(container)[0]
    await loadsAs(img, 42, 680)
    expect(img.dataset.wide).toBe('0')
  })

  it('does not leave the verdict behind when the same element is reused', async () => {
    // An <img> that has already loaded is reused when its src changes, and a
    // stale `1` would stand a portrait scan on its side. So the attribute is
    // written on every load rather than only when it is true.
    const { container } = await shelf()
    const img = spines(container)[0]
    await loadsAs(img, 680, 115)
    expect(img.dataset.wide).toBe('1')
    await loadsAs(img, 42, 680)
    expect(img.dataset.wide).toBe('0')
  })

  it('treats a square scan as upright rather than turning it', async () => {
    // The tie has to fall somewhere, and not turning is the side that cannot
    // make a correct scan worse.
    const { container } = await shelf()
    const img = spines(container)[0]
    await loadsAs(img, 300, 300)
    expect(img.dataset.wide).toBe('0')
  })
})
