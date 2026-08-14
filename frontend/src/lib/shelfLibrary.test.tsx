/**
 * Shelf's shelf, driven by the pad, against the real host and the real SDK.
 *
 * The screen is a pair: the host owns the cursor and Shelf draws it, and both
 * halves of that pair had the same defect from opposite ends. So both are
 * exercised through the assembly rather than in isolation — a stub host would
 * have passed on the day the real one lost four presses out of five.
 *
 * What is asserted is what can be asserted from here: where the cursor ends
 * up, which column the markup marks as selected, which DOM node draws which
 * game, and how much of the row is standing. How it *looks* on a television is the owner's to judge, and is
 * not claimed anywhere below.
 */
import { render, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React, { createElement } from 'react'
import { buildSdk } from './themeSdk'
import { useStore } from '../store'
import LibraryScreen from '../components/LibraryScreen'

const THEME = '../../../config/themes/shelf'

/**
 * The stage's width, as the shelf will measure it.
 *
 * jsdom lays nothing out, so the one number the row has to be sized against
 * has to be supplied. 1434 is what the box gives it at 1080p: 1920, less the
 * library's 2×30 padding, less the 26px gap, less the 400px card.
 */
const STAGE_W = 1434
/** `--pitch` on `.cz-rail` for the default stacking. */
const PITCH = 40

const stubStageWidth = (w: number) => {
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() { return (this as HTMLElement).classList.contains('cz-stage') ? w : 0 },
  })
}

const GAMES = Array.from({ length: 80 }, (_, i) => ({
  filename: `game-${String(i).padStart(3, '0')}.rom`,
  display_name: `Game ${String(i).padStart(3, '0')}`,
  path: `/roms/game-${i}.rom`,
  ext: '.rom',
}))

beforeEach(() => {
  stubStageWidth(STAGE_W)
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

const slotOffsets = (c: HTMLElement) =>
  [...c.querySelectorAll('.cz-slot')]
    .map(el => Number(/--o:\s*(-?\d+)/.exec(el.getAttribute('style') ?? '')?.[1] ?? NaN))

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

describe('Shelf’s shelf — how much of the row is standing', () => {
  it('mounts a row wider than the stage it is drawn in', async () => {
    // Why this is not a detail. The rail is one element that slides; the
    // spines sit inside it and have no animation of their own. So the only way
    // a spine can appear to MOVE on its own is to be mounted, or dropped,
    // while the rail is sliding — and a row that ends before the stage does
    // gets exactly that, once per step, at the far end of the shelf.
    //
    // The row was a constant 12 columns either side: ±480px at a 40px pitch,
    // inside a stage 717px wide either side of centre at 1080p.
    //
    // Half the stage plus one column is the least that cannot be caught doing
    // it. Whether it then LOOKS right is not something this file can say.
    const { container } = await shelf()
    await act(async () => { await new Promise(res => setTimeout(res, 50)) })
    const idx = useStore.getState().selectedGameIdx
    const reach = Math.max(...slotOffsets(container).map(o => Math.abs(o - idx))) * PITCH
    expect(reach).toBeGreaterThanOrEqual(STAGE_W / 2)
  })

  it('grows the row rather than the gap when the stage gets wider', async () => {
    // `gallery` moves the card to the bottom and hands the whole screen to the
    // stage, so a count that was right for the shelf is short by another 400px
    // there. Nothing about the row may be a constant.
    const { container } = await shelf()
    await act(async () => { await new Promise(res => setTimeout(res, 50)) })
    const narrow = slotOffsets(container).length

    stubStageWidth(1860)
    await act(async () => { window.dispatchEvent(new Event('resize')); await new Promise(res => setTimeout(res, 0)) })

    const idx = useStore.getState().selectedGameIdx
    const wide = slotOffsets(container)
    expect(wide.length).toBeGreaterThan(narrow)
    expect(Math.max(...wide.map(o => Math.abs(o - idx))) * PITCH).toBeGreaterThanOrEqual(1860 / 2)
  })

  it('still costs one new column per step, not a fresh screenful', async () => {
    // The reason the old count was small, and a promise the measured one has
    // to keep: walking the shelf must not remount the row. Everything that was
    // standing and still is must be the same node, and at most one column may
    // be new.
    const { container } = await shelf()
    act(() => { useStore.setState({ selectedGameIdx: 40 }) })
    await settle()

    const label = (el: Element) => el.querySelector('.cz-spine')?.getAttribute('aria-label') ?? ''
    const before = new Map([...container.querySelectorAll('.cz-slot')].map(el => [label(el), el]))

    await burst('gp:dpad-right', 1)
    await settle()

    const after = [...container.querySelectorAll('.cz-slot')]
    const fresh = after.filter(el => !before.has(label(el)))
    expect(fresh).toHaveLength(1)
    expect(after.filter(el => before.get(label(el)) === el))
      .toHaveLength(after.length - fresh.length)
  })
})
