/**
 * Shelf remembers how you like to read a library.
 *
 * R2 cycles the library between three layouts. It used to be `useState('shelf')`
 * and nothing else, so leaving a console and coming back put it straight back
 * to the first one — three presses to get to Gallery, every single time, and
 * again after a power cycle.
 *
 * What is asserted here is the pair that matters: the layout survives a
 * REMOUNT (walking out of the library and back in), and it survives a cold
 * start (a fresh mount with nothing in memory but the stored value). The flip
 * deliberately does neither — see the note in lib/browse.js.
 */
import { render, act, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React, { createElement } from 'react'
import { buildSdk } from './themeSdk'
import { useStore } from '../store'
import LibraryScreen from '../components/LibraryScreen'

const THEME = '../../../config/themes/shelf'
const KEY = 'gc:shelf:libraryMode'

const GAMES = Array.from({ length: 6 }, (_, i) => ({
  filename: `game-${i}.rom`,
  display_name: `Game ${i}`,
  path: `/roms/game-${i}.rom`,
  ext: '.rom',
}))

beforeEach(() => {
  localStorage.clear()
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() { return (this as HTMLElement).classList.contains('cz-stage') ? 1434 : 0 },
  })
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(typeof input === 'string' ? input : (input as Request).url ?? input)
    const body: unknown = url.includes('/games') ? GAMES
      : url.includes('/systems/') ? { id: 'gc', label: 'GameCube', color: '#6a5acd' }
        : []
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
  useStore.setState({
    screen: 'library', selectedSystemId: 'gc', selectedGameIdx: 0,
    modalDepth: 0, sessionGameKey: null,
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  localStorage.clear()
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

const layout = (c: HTMLElement) =>
  c.querySelector('.cz-lib')?.getAttribute('data-view') ?? null

const pressR2 = (n = 1) => act(async () => {
  for (let i = 0; i < n; i++) window.dispatchEvent(new CustomEvent('gp:r2'))
})

describe('Shelf — the layout the player chose', () => {
  it('starts on the shelf when nothing was ever chosen', async () => {
    const { container } = await shelf()
    expect(layout(container)).toBe('shelf')
  })

  it('cycles through the three layouts on R2', async () => {
    const { container } = await shelf()
    await pressR2()
    expect(layout(container)).toBe('stack')
    await pressR2()
    expect(layout(container)).toBe('gallery')
    await pressR2()
    expect(layout(container)).toBe('shelf')
  })

  it('writes the choice down where a power cycle cannot reach it', async () => {
    await shelf()
    await pressR2(2)
    expect(localStorage.getItem(KEY)).toBe('gallery')
  })

  it('survives leaving the library and coming back', async () => {
    // The defect, exactly: this is what walking out of a console and into
    // another one does — the hook unmounts and mounts again.
    const first = await shelf()
    await pressR2(2)
    expect(layout(first.container)).toBe('gallery')
    cleanup()

    const again = await shelf()
    expect(layout(again.container)).toBe('gallery')
  })

  it('survives a cold start, with nothing in memory but the stored value', async () => {
    localStorage.setItem(KEY, 'stack')
    const { container } = await shelf()
    expect(layout(container)).toBe('stack')
  })

  it('cycles on from the layout it was restored to, not from the first', async () => {
    // The bindings are registered once with `[]`, so a `mode` read from that
    // closure would be for ever its value at mount and R2 would bounce between
    // two layouts. That is what `modeRef` is for.
    localStorage.setItem(KEY, 'stack')
    const { container } = await shelf()
    await pressR2()
    expect(layout(container)).toBe('gallery')
  })

  it('ignores a stored value that is not a layout', async () => {
    // Someone editing devtools, or a key this theme used to mean something
    // else by. A library that does not draw is not an acceptable answer.
    localStorage.setItem(KEY, 'not-a-layout')
    const { container } = await shelf()
    expect(layout(container)).toBe('shelf')
  })

  it('still draws when storage refuses to answer', async () => {
    const boom = () => { throw new Error('storage disabled') }
    const spyGet = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(boom)
    const spySet = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(boom)
    try {
      const { container } = await shelf()
      expect(layout(container)).toBe('shelf')
      await pressR2()
      expect(layout(container)).toBe('stack')   // the session still works
    } finally {
      spyGet.mockRestore()
      spySet.mockRestore()
    }
  })
})
