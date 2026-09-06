/**
 * The jacket coming out of the shelf, and what a second press does to it.
 *
 * Two defects from the 2026-09-04 audit (findings 4 and 5), both on the same
 * gesture and both about time rather than about pixels.
 *
 *   · The travel and the turn ran on two different clocks. The holder was
 *     keyed on the cursor and mounted on the press; the solid inside it was
 *     keyed on the settled selection and therefore replaced 150 ms later, with
 *     a fresh animation. Measured in a browser half a second after a step: 500
 *     ms elapsed on the travel, 333 ms on the turn — the box had set off down
 *     the shelf and was still standing edge-on.
 *
 *   · A second press half a second in deleted the outgoing jacket and re-hid
 *     the arriving one, leaving nothing on the stage at all. That was written
 *     for a burst, where nothing has come out yet and there is nothing to
 *     preserve; applied to a jacket already standing at the front, it deletes
 *     what the player is looking at.
 *
 * jsdom runs no animations, so what is asserted here is the structure they run
 * on: which node draws which game, whether one node is replaced while its
 * animation would be running, and how many solids are on the stage. How it
 * looks on a television is the owner's to judge and is not claimed below.
 */
import { render, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React, { createElement } from 'react'
import { buildSdk } from './themeSdk'
import { useStore } from '../store'
import LibraryScreen from '../components/LibraryScreen'

const THEME = '../../../config/themes/shelf'
const STAGE_W = 1434

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
  // Real time is not a clock this test can read. The gesture is 920 ms long
  // and jsdom takes a sizeable fraction of that to render eighty spines, so
  // "press, wait 100 ms, press" ran past the 360 ms handover on a slow machine
  // and exercised the opposite branch. Driven timers make each press land
  // exactly where the test says it does.
  vi.useFakeTimers()
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
  vi.useRealTimers()
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
  const r = render(createElement(LibraryScreen as React.ComponentType<{ view: unknown; omit: string[] }>,
    { view: View, omit: ['options'] }))
  await wait(0)
  return r
}

const press = async (event: string) => {
  await act(async () => { window.dispatchEvent(new CustomEvent(event)) })
}

const wait = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })
/** Longer than PUSH_MS + 560, so the whole gesture is over. */
const settle = () => wait(1200)

const arriving = (c: HTMLElement) => c.querySelector('.cz-hold[data-phase="in"]')
const solids = (c: HTMLElement) => [...c.querySelectorAll('.cz-hold')]
  .filter(n => n.getAttribute('data-tucked') !== '1')

describe('the jacket and the clock it moves on', () => {
  it('never replaces the solid inside a holder that is already animating', async () => {
    const { container } = await shelf(); await settle()
    const h0 = arriving(container)
    const b0 = h0?.querySelector('.cz-box')

    await press('gp:dpad-right')
    await wait(20)                       // before the artwork settles
    const h1 = arriving(container)
    const b1 = h1?.querySelector('.cz-box')

    await wait(300)                      // after it
    const h2 = arriving(container)
    const b2 = h2?.querySelector('.cz-box')

    // The invariant, and the whole of finding 4: a new solid is a new holder.
    // The travel runs on the holder and the turn on the solid, so a solid
    // rebuilt underneath a surviving holder is a gesture on two clocks — 500
    // ms elapsed on one and 333 on the other, measured in a browser.
    expect(b2 === b1).toBe(h2 === h1)
    expect(b1 === b0).toBe(h1 === h0)
    expect(b2).not.toBe(b0)              // and it did follow the cursor
  })

  it('pays back the settle delay so the jacket still comes out on time', async () => {
    // The arriving holder is mounted when the selection settles, 150 ms after
    // the press, and its CSS delay exists to let the outgoing jacket land
    // first. Counted from the mount it would arrive 150 ms late — and the row
    // gives its column up on the press's clock, not the mount's, so those 150
    // ms are exactly the window in which two spines are drawn in one column.
    const { container } = await shelf(); await settle()
    await press('gp:dpad-right')
    await wait(200)
    const style = arriving(container)?.getAttribute('style') ?? ''
    const wait_ms = Number(/--wait:\s*(\d+)ms/.exec(style)?.[1] ?? NaN)
    expect(wait_ms).toBeGreaterThan(100)
    expect(wait_ms).toBeLessThan(320)
  })

  it('draws the game its holder is keyed on, never the previous one', async () => {
    const { container } = await shelf(); await settle()
    await press('gp:dpad-right')
    await settle()
    // The card names the settled game; the box must be the same game.
    const name = container.querySelector('.cz-card-name')?.textContent
    const alt = arriving(container)?.querySelector('.cz-f-front img')?.getAttribute('alt')
    expect(alt).toBe(name)
  })
})

describe('a second press, and what is left standing', () => {
  it('keeps a solid on the stage when the jacket is already out', async () => {
    const { container } = await shelf(); await settle()
    await press('gp:dpad-right')
    await wait(500)
    // The arriving jacket has come out of the row by now.
    expect(arriving(container)?.getAttribute('data-tucked')).toBe('0')

    await press('gp:dpad-right')
    expect(solids(container).length).toBeGreaterThan(0)
    await wait(50)
    expect(solids(container).length).toBeGreaterThan(0)
  })

  it('still slides with nothing in hand during a real burst', async () => {
    // Presses inside the wait before anything comes out: no outgoing jacket,
    // the row simply moves. This is the behaviour the cancellation was written
    // for and it is deliberately kept — there is nothing on screen to preserve.
    const { container } = await shelf(); await settle()
    await press('gp:dpad-right')
    await wait(100)
    await press('gp:dpad-right')
    await wait(100)
    await press('gp:dpad-right')
    expect(container.querySelector('.cz-hold[data-phase="out"]')).toBeNull()
    expect(arriving(container)?.getAttribute('data-tucked')).toBe('1')
    // And it ends with the jacket out, once the player stops.
    await settle()
    expect(arriving(container)?.getAttribute('data-tucked')).toBe('0')
    expect(useStore.getState().selectedGameIdx).toBe(3)
  })
})
