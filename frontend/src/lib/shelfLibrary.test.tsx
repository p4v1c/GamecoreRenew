/**
 * Shelf's shelf, driven by the pad, against the real host and the real SDK.
 *
 * The screen is a pair: the host owns the cursor and Shelf draws it, and both
 * halves of that pair had the same defect from opposite ends. So both are
 * exercised through the assembly rather than in isolation — a stub host would
 * have passed on the day the real one lost four presses out of five.
 *
 * What is asserted is what can be asserted from here: where the cursor ends
 * up, which column the markup marks as selected, and which DOM node draws
 * which game. How it *looks* on a television is the owner's to judge, and is
 * not claimed anywhere below.
 */
import { render, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React, { createElement } from 'react'
import { buildSdk } from './themeSdk'
import { useStore } from '../store'
import LibraryScreen from '../components/LibraryScreen'

const THEME = '../../../config/themes/shelf'

const GAMES = Array.from({ length: 80 }, (_, i) => ({
  filename: `game-${String(i).padStart(3, '0')}.rom`,
  display_name: `Game ${String(i).padStart(3, '0')}`,
  path: `/roms/game-${i}.rom`,
  ext: '.rom',
}))

beforeEach(() => {
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

afterEach(async () => {
  const { cleanup } = await import('@testing-library/react')
  cleanup()
  vi.unstubAllGlobals()
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
  // Shelf declares `libraryOmit: ['options']`; passing it keeps the assembly
  // the same one index.js builds.
  const r = render(createElement(LibraryScreen as React.ComponentType<{ view: unknown; omit: string[] }>,
    { view: View, omit: ['options'] }))
  await act(async () => { await new Promise(res => setTimeout(res, 0)) })
  return r
}

const burst = async (event: string, n: number) => {
  await act(async () => {
    for (let i = 0; i < n; i++) window.dispatchEvent(new CustomEvent(event))
  })
}

const settle = () => act(async () => { await new Promise(res => setTimeout(res, 1200)) })

const railIndex = (c: HTMLElement) =>
  Number(/--i:\s*(-?\d+)/.exec(c.querySelector('.cz-rail')?.getAttribute('style') ?? '')?.[1] ?? NaN)

describe('Shelf’s shelf — walking it fast', () => {
  it('takes one step per press of ← and →', async () => {
    // Shelf binds ←→ itself, to the host's own selection callback. It had the
    // host's bug by a different route: the index it stepped from was written
    // during render, so a press that arrived before the next render stepped
    // from where the cursor had already been.
    await shelf()
    await burst('gp:dpad-right', 6)
    expect(useStore.getState().selectedGameIdx).toBe(6)
    await burst('gp:dpad-left', 2)
    expect(useStore.getState().selectedGameIdx).toBe(4)
  })

  it('still stops at both ends of the row', async () => {
    await shelf()
    await burst('gp:dpad-left', 3)
    expect(useStore.getState().selectedGameIdx).toBe(0)
    await burst('gp:dpad-right', GAMES.length + 30)
    expect(useStore.getState().selectedGameIdx).toBe(GAMES.length - 1)
  })

  it('agrees with itself once the burst is over', async () => {
    // The question that decides whether this is a rendering fault or a cursor
    // fault: after a rafale, does the column the markup marks as selected
    // still name the game the cursor is on?
    const { container } = await shelf()
    await burst('gp:dpad-right', 9)
    await settle()

    const idx = useStore.getState().selectedGameIdx
    expect(idx).toBe(9)
    expect(railIndex(container)).toBe(idx)

    const on = [...container.querySelectorAll('.cz-slot[data-on="1"]')]
    expect(on).toHaveLength(1)
    expect(on[0].querySelector('.cz-spine')?.getAttribute('aria-label')).toBe('Game 009')
  })

  it('does not move the shelf while a modal owns the pad', async () => {
    await shelf()
    act(() => { useStore.setState({ modalDepth: 1 }) })
    await burst('gp:dpad-right', 5)
    expect(useStore.getState().selectedGameIdx).toBe(0)
  })

  it('keeps every spine that stays on screen as the same element', async () => {
    // The first thing suspected, asked directly, and the answer is no: a row
    // keyed by position would recycle a node for another game on every step,
    // and a transition meant for a few pixels would animate a jump across the
    // shelf. The columns are keyed by filename and they do not. Kept because
    // it is the assumption the rest of the shelf's animation rests on, and
    // nothing else states it.
    const { container } = await shelf()
    await act(async () => { await new Promise(res => setTimeout(res, 50)) })
    const label = (el: Element) => el.querySelector('.cz-spine')?.getAttribute('aria-label') ?? ''
    const before = new Map([...container.querySelectorAll('.cz-slot')].map(el => [label(el), el]))

    await burst('gp:dpad-right', 1)
    await settle()

    const after = [...container.querySelectorAll('.cz-slot')]
    const stillHere = after.filter(el => before.has(label(el)))
    expect(stillHere.filter(el => before.get(label(el)) === el)).toHaveLength(stillHere.length)
    expect(stillHere.length).toBeGreaterThan(0)
  })
})
