/**
 * The jacket put back into the shelf and the next one taken out.
 *
 * The gesture used to be two keyframe animations on two keyed holders. A
 * keyframe cannot be interrupted, only cancelled, so a second press inside the
 * 360 ms put-back deleted the outgoing jacket mid-turn and kept the next one
 * hidden: tapping → at any ordinary pace showed no animation at all. And the
 * jacket going back was a NEW holder with a new solid, so its scans loaded
 * again and the faces painted board-black until they had (the black flash).
 *
 * lib/swap.js replaced both with one progress value per jacket, moved every
 * animation frame. jsdom draws nothing, so what is asserted is the structure
 * that guarantees the motion: a jacket's elements are never replaced while it
 * moves, a jacket leaves the stage only when it is back in its column, every
 * press in a burst has a jacket on stage, and a box sent back mid-way turns
 * from the angle it had rather than jumping. How it looks on a television is
 * the owner's to judge; docs/dev-log/shelf-studio-home.md has the frames.
 */
import { render, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React, { createElement } from 'react'
import { buildSdk } from '../lib/themeSdk'
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
  // requestAnimationFrame and performance too: the swap is driven per frame.
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
    'Date', 'requestAnimationFrame', 'cancelAnimationFrame', 'performance'] })
  stubStageWidth(STAGE_W)
  // lib/front.js remembers each game's front for the session; each test is a new session.
  vi.resetModules()
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

const holder = (c: HTMLElement, i: number) =>
  c.querySelector(`.cz-hold[data-game="${GAMES[i].filename}"]`) as HTMLElement | null
const holders = (c: HTMLElement) => [...c.querySelectorAll('.cz-hold')] as HTMLElement[]
/** The angle the solid is turned to, from the transform the swap writes on it. */
const turn = (h: HTMLElement | null) => {
  const t = (h?.querySelector('.cz-box') as HTMLElement | null)?.style.transform || ''
  const m = /rotateY\((-?[\d.]+)deg\)/.exec(t)
  return m ? Number(m[1]) : null
}
const gap = (c: HTMLElement, i: number) =>
  [...c.querySelectorAll('.cz-slot')].find((s) => s.querySelector(`[aria-label="Game ${String(i).padStart(3, '0')}"]`))
    ?.getAttribute('data-gap')

describe('the jacket and the frames it moves on', () => {
  it('never replaces a jacket while it moves, and hands the rest pose back to CSS', async () => {
    const { container } = await shelf(); await settle()
    await press('gp:dpad-right')
    await wait(400)
    const h1 = holder(container, 1)
    const b1 = h1?.querySelector('.cz-box')
    expect(h1).not.toBeNull()
    await wait(200)                      // the artwork has settled by now
    expect(holder(container, 1)).toBe(h1)
    expect(holder(container, 1)?.querySelector('.cz-box')).toBe(b1)
    await settle()
    expect(holder(container, 1)).toBe(h1)
    // In the hand and still: the stylesheet owns the pose again (and the flip).
    expect((h1?.querySelector('.cz-box') as HTMLElement).style.transform).toBe('')
  })

  it('puts the last box back into its column instead of deleting it', async () => {
    const { container } = await shelf(); await settle()
    const h0 = holder(container, 0)
    await press('gp:dpad-right')
    await wait(50)
    expect(holder(container, 0)).toBe(h0)        // still on stage, same element
    expect(gap(container, 0)).toBe('1')          // its column is still empty
    await settle()
    expect(holder(container, 0)).toBeNull()      // home, and drawn by the row again
    expect(gap(container, 0)).toBe('0')
  })

  it('draws the game its holder is keyed on, never the previous one', async () => {
    const { container } = await shelf(); await settle()
    await press('gp:dpad-right')
    await settle()
    const name = container.querySelector('.cz-card-name')?.textContent
    const alt = holder(container, 1)?.querySelector('.cz-f-front img')?.getAttribute('alt')
    expect(alt).toBe(name)
    expect(holders(container)).toHaveLength(1)
  })
})

describe('a burst on the d-pad', () => {
  it('always has a jacket on stage, and ends with the right one in hand', async () => {
    const { container } = await shelf(); await settle()
    for (let i = 0; i < 4; i++) {
      await press('gp:dpad-right')
      for (let t = 0; t < 120; t += 20) {
        await wait(20)
        expect(holders(container).length).toBeGreaterThan(0)
      }
    }
    await settle(); await settle()
    expect(useStore.getState().selectedGameIdx).toBe(4)
    expect(holders(container).map((h) => h.getAttribute('data-game'))).toEqual([GAMES[4].filename])
  })

  it('turns a box sent back mid-way from the angle it had, without a jump', async () => {
    const { container } = await shelf(); await settle()
    await press('gp:dpad-right')
    // Long enough for the next box to be part way through turning to face you.
    let before: number | null = null
    for (let t = 0; t < 900 && !(before != null && before < 80); t += 16) {
      await wait(16); before = turn(holder(container, 1))
    }
    expect(before).not.toBeNull()
    expect(before!).toBeLessThan(80)
    const h1 = holder(container, 1)
    await press('gp:dpad-right')
    await wait(16)
    const after = turn(holder(container, 1))
    expect(holder(container, 1)).toBe(h1)        // same element, not a new one
    expect(after).not.toBeNull()
    expect(after!).toBeGreaterThanOrEqual(before!)  // heading back to edge-on…
    expect(after! - before!).toBeLessThan(30)       // …from where it was
  })
})

describe('a jacket whose front is not decoded yet', () => {
  /** Image whose decode() settles only when the test says so. */
  const pending: Array<{ src: string, settle: (ok: boolean) => void }> = []
  class SlowImage {
    src = ''
    decoding = 'auto'
    decode() {
      return new Promise<void>((ok, no) => {
        pending.push({ src: this.src, settle: (good) => (good ? ok() : no(new Error('broken'))) })
      })
    }
  }
  const front = (i: number) => pending.find((p) => p.src.endsWith(encodeURIComponent(GAMES[i].filename)))

  beforeEach(() => { pending.length = 0; vi.stubGlobal('Image', SlowImage) })

  it('comes out edge-on and turns to face you only once its scan is decoded', async () => {
    const { container } = await shelf(); await settle()
    front(0)?.settle(true); await settle()
    await press('gp:dpad-right')
    await settle(); await settle()
    // Out of the row but still edge-on (rotateY 90): the unprinted card never shows.
    expect(turn(holder(container, 1))).toBe(90)
    front(1)!.settle(true)
    await settle()
    expect((holder(container, 1)?.querySelector('.cz-box') as HTMLElement).style.transform).toBe('')
  })

  it('turns anyway when the scan fails, so the printed fallback shows', async () => {
    const { container } = await shelf(); await settle()
    front(0)!.settle(false)
    await settle()
    expect((holder(container, 0)?.querySelector('.cz-box') as HTMLElement).style.transform).toBe('')
  })
})

describe('a cover that is not a box front', () => {
  // PS3 and PSP covers are the disc's ICON0, a 320x176 logo banner. The game's
  // box-front scan is the real sleeve; the banner must never be drawn as a box.
  const COVER = /\/api\/covers\//
  const BOX_FRONT = /\/media\/box-front$/
  let sizes: (src: string) => [number, number] | null
  class SizedImage {
    src = ''
    decoding = 'auto'
    naturalWidth = 0
    naturalHeight = 0
    decode() {
      const size = sizes(this.src)
      if (!size) return Promise.reject(new Error('404'))
      ;[this.naturalWidth, this.naturalHeight] = size
      return Promise.resolve()
    }
  }
  beforeEach(() => { vi.stubGlobal('Image', SizedImage) })

  const front = (c: HTMLElement, i: number) => holder(c, i)?.querySelector('.cz-f-front img')?.getAttribute('src') ?? null
  const ratio = (c: HTMLElement, i: number) =>
    Number((holder(c, i)?.querySelector('.cz-box') as HTMLElement | null)?.style.getPropertyValue('--ratio'))

  it('draws the box-front scan at its own shape and never shows the banner', async () => {
    sizes = (src) => COVER.test(src) ? [320, 176] : BOX_FRONT.test(src) ? [581, 680] : [300, 400]
    const { container } = await shelf()
    for (let t = 0; t < 1500; t += 16) {
      await wait(16)
      expect(front(container, 0) ?? '').not.toMatch(COVER)
    }
    expect(front(container, 0)).toMatch(BOX_FRONT)
    expect(ratio(container, 0)).toBeCloseTo(581 / 680, 3)
  })

  it('falls back to the banner, clamped, when the game has no box-front', async () => {
    sizes = (src) => COVER.test(src) ? [320, 176] : null
    const { container } = await shelf(); await settle()
    expect(front(container, 0)).toMatch(COVER)
    expect(ratio(container, 0)).toBe(1.5)
  })

  it('keeps a cover that is a box front, at its own shape', async () => {
    sizes = (src) => COVER.test(src) ? [600, 420] : BOX_FRONT.test(src) ? [581, 680] : null
    const { container } = await shelf(); await settle()
    expect(front(container, 0)).toMatch(COVER)
    expect(ratio(container, 0)).toBeCloseTo(600 / 420, 3)
  })
})
