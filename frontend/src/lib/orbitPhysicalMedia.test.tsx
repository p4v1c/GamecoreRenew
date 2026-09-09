/**
 * Orbit's cartridge/disc art, and the request budget behind it.
 *
 * The theme draws a physical cartridge or disc for every game in the library,
 * and the artwork that makes it a photograph rather than a drawing lives
 * behind `media.list()` — one HTTP round trip per game, and on an unscraped
 * game a real trip to the scraper.
 *
 * A library of four hundred games is normal, and the grid renders all of them.
 * So the interesting property is not "does a card draw" but "how many requests
 * does a screenful of cards cost", and the answer has to be *not one per card*
 * however fast somebody scrolls. Two things get it there and both are asserted
 * below: only the settled selection may ask at all, and the backdrop and the
 * cartridge share one cache and one in-flight request rather than each keeping
 * their own.
 *
 * How the cartridge LOOKS is the owner's to judge and is claimed nowhere here.
 */
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import React, { createElement, useEffect, useMemo, useRef, useState } from 'react'
import htm from 'htm'
import { buildSdk } from './themeSdk'
import { useStore } from '../store'

const THEME = '../../../config/themes/orbit'

const flush = (ms = 0) => act(async () => { await new Promise(r => setTimeout(r, ms)) })

/**
 * Wait past the debounce, generously.
 *
 * Real timers rather than a faked clock: every one of these tests dynamically
 * imports the theme, and module loading is real I/O that a faked clock does
 * not drive. The waits are therefore *lower* bounds — long enough that the
 * debounce has certainly expired on a loaded machine — and every assertion
 * they lead to is written to be stable once it has. A "how many requests"
 * assertion does not grow with extra waiting: only one selection is active,
 * and it may ask once.
 */
const settle = (ms = 600) => flush(ms)

/** Heavy enough to need more than the 5 s default on a loaded runner. */
const SLOW = 30_000

/** A fresh module graph: the cache these tests are about is module state. */
async function loadOrbit() {
  vi.resetModules()
  const [cache, physical, backdrop] = await Promise.all([
    import(/* @vite-ignore */ `${THEME}/lib/media-cache.js`),
    import(/* @vite-ignore */ `${THEME}/lib/physical-media.js`),
    import(/* @vite-ignore */ `${THEME}/lib/backdrop.js`),
  ])
  return { ...cache, ...physical, ...backdrop }
}

/** The same `ui` surface `buildSdk` hands a theme — the theme renders with it. */
const ui = {
  html: htm.bind(React.createElement),
  React, useState, useEffect, useRef, useMemo,
}

/** An SDK whose media tier is a counter. */
function fakeSdk(list: ReturnType<typeof vi.fn>) {
  return {
    ui,
    api: {
      media: {
        list,
        url: (systemId: string, filename: string, type: string) =>
          `/api/media/${systemId}/${filename}/media/${type}`,
      },
    },
  }
}

const withArt = (...types: string[]) => ({
  media: Object.fromEntries(types.map(t => [t, { kind: 'image' }])),
})

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

// ── the request budget, on a library the size of a real one ──────────────────

describe('a library of two hundred games', () => {
  const systems = [{ id: 'rpcs3', label: 'RPCS3', kind: 'emulator', iconPath: 'rpcs3.svg' }]
  const games = Array.from({ length: 220 }, (_, i) => ({
    filename: `Game${String(i).padStart(3, '0')}.iso`,
    display_name: `Game ${i}`,
    path: `/test/Game${i}.iso`,
  }))
  let mediaCalls: string[] = []

  beforeEach(() => {
    mediaCalls = []
    useStore.setState({
      screen: 'home', selectedSystemId: null, selectedGameIdx: 0, gridFocusIdx: 0,
      gridPage: 0, modalDepth: 0, standby: 'off', powerPending: null,
      sessionGameKey: null, sessionSystemId: null, backgroundSessions: [],
    })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/media/')) mediaCalls.push(url)
      const body = url.endsWith('/systems') ? systems
        : url.endsWith('/systems/rpcs3') ? systems[0]
          : url.endsWith('/systems/rpcs3/games') ? games
            : url.includes('/playtime') ? []
              : url.includes('/metadata/') ? { found: false }
                : url.includes('/media/') ? withArt('fanart-background', 'cart-front')
                  : url.endsWith('/sysinfo') ? { controllers: [], ip: '192.0.2.1' }
                    : url.includes('/settings') ? {}
                      : { ok: true }
      return { ok: true, status: 200, json: async () => body }
    }))
  })

  async function openLibrary() {
    vi.resetModules()
    const { default: createOrbit } = await import(/* @vite-ignore */ `${THEME}/index.js`)
    const sdk = buildSdk('orbit', { selectTheme: vi.fn(async () => {}) })
    const r = render(createElement(createOrbit(sdk).shell))
    await flush()
    await act(async () => { fireEvent.click(r.getByText('Library', { selector: '.nav-item' })) })
    await waitFor(() => expect(r.container.querySelectorAll('.library-card').length)
      .toBeGreaterThan(200))
    return r
  }

  it('draws every card without asking the media tier about any of them', async () => {
    const r = await openLibrary()
    expect(r.container.querySelectorAll('.library-card')).toHaveLength(220)

    // Before anything has settled: a card is a cartridge drawn in CSS, and a
    // cartridge costs nothing to draw. This is the property the whole design
    // exists for — 220 cards must not be 220 round trips.
    expect(mediaCalls.length).toBeLessThanOrEqual(1)
    // Scoped to the grid: the home rail draws physical art too, and this
    // assertion is about the library's cards.
    expect(r.container.querySelectorAll('.library-grid .orbit-physical').length).toBe(220)
  }, SLOW)

  it('spends at most one lookup per settled game, however many are on screen', async () => {
    const r = await openLibrary()
    await settle()
    const settled = new Set(mediaCalls.map(u => u.split('/media/')[1]?.split('/')[1]))
    // One game is selected, so at most that one game may have been looked up.
    expect(settled.size).toBeLessThanOrEqual(1)
    expect(r.container.querySelectorAll('.library-card').length).toBe(220)
  }, SLOW)

  it('does not turn a fast scroll into one request per game passed', async () => {
    // The reason the lookup is debounced rather than fired on selection. A
    // player crossing the library with the stick held down passes hundreds of
    // games in a couple of seconds; each one settling for 175 ms is what makes
    // that a handful of requests instead of hundreds.
    const r = await openLibrary()
    mediaCalls.length = 0
    // One burst, not sixty separate moments: awaiting between presses would
    // let each game settle and would measure the test's own pace instead.
    await act(async () => {
      for (let i = 0; i < 60; i++) window.dispatchEvent(new CustomEvent('gp:dpad-right'))
    })
    await settle()
    expect(mediaCalls.length).toBeLessThanOrEqual(2)
    expect(r.container.querySelectorAll('.library-card').length).toBe(220)
  }, SLOW)
})

// ── one cache, shared ────────────────────────────────────────────────────────

describe('the media index cache', () => {
  it('asks once for a game and answers the second caller from memory', async () => {
    const { listMediaIndex } = await loadOrbit()
    const list = vi.fn().mockResolvedValue(withArt('disc'))
    const sdk = fakeSdk(list)

    await listMediaIndex(sdk, 'pcsx2', 'Ico.iso')
    await listMediaIndex(sdk, 'pcsx2', 'Ico.iso')
    expect(list).toHaveBeenCalledTimes(1)
  })

  it('gives two callers racing for the same game one request between them', async () => {
    // The backdrop and the cartridge are two components resolving the same
    // game in the same frame. Without the in-flight map that is two identical
    // requests, every time, for every game the player stops on.
    const { listMediaIndex } = await loadOrbit()
    let answer!: (v: unknown) => void
    const list = vi.fn().mockImplementation(() => new Promise(r => { answer = r }))
    const sdk = fakeSdk(list)

    const both = Promise.all([
      listMediaIndex(sdk, 'rpcs3', 'Journey.iso'),
      listMediaIndex(sdk, 'rpcs3', 'Journey.iso'),
    ])
    answer(withArt('background'))
    const [a, b] = await both

    expect(list).toHaveBeenCalledTimes(1)
    expect(a).toEqual(b)
  })

  it('keeps a failure retryable instead of remembering it', async () => {
    // A backend restarting, or a scraper that timed out once, must not blank a
    // game for the life of the page.
    const { listMediaIndex } = await loadOrbit()
    const list = vi.fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue(withArt('cart-front'))
    const sdk = fakeSdk(list)

    await listMediaIndex(sdk, 'ryujinx', 'Zelda.xci').catch(() => {})
    const second = await listMediaIndex(sdk, 'ryujinx', 'Zelda.xci')

    expect(list).toHaveBeenCalledTimes(2)
    expect(second.media['cart-front']).toBeTruthy()
  })

  it('answers a box with no media tier at all without asking', async () => {
    const { listMediaIndex } = await loadOrbit()
    const answer = await listMediaIndex({ ui, api: { media: {} } }, 'x', 'y.iso')
    expect(answer).toEqual({ media: {} })
  })

  it('keeps two games apart', async () => {
    const { listMediaIndex } = await loadOrbit()
    const list = vi.fn().mockResolvedValue(withArt('disc'))
    const sdk = fakeSdk(list)

    await listMediaIndex(sdk, 'pcsx2', 'Ico.iso')
    await listMediaIndex(sdk, 'pcsx2', 'Sotc.iso')
    expect(list).toHaveBeenCalledTimes(2)
  })
})

describe('the backdrop and the cartridge, on the same game', () => {
  it('cost one request between them, not one each', async () => {
    // Both resolve the same `media.list()` answer for different pictures out
    // of it. Sharing the cache is what makes a settled game one round trip.
    const { listMediaIndex, createPhysicalMedia } = await loadOrbit()
    const list = vi.fn().mockResolvedValue(withArt('fanart-background', 'cart-front'))
    const sdk = fakeSdk(list)

    const PhysicalMedia = createPhysicalMedia(sdk)
    render(createElement(PhysicalMedia, {
      systemId: 'ryujinx', filename: 'Zelda.xci', ext: 'xci', title: 'Zelda', active: true,
    }))
    await settle()
    await listMediaIndex(sdk, 'ryujinx', 'Zelda.xci')

    expect(list).toHaveBeenCalledTimes(1)
  })
})

// ── the cartridge itself ─────────────────────────────────────────────────────

describe('what a game is drawn as', () => {
  it('reads the platform first, because .bin says nothing on its own', async () => {
    const { physicalKind } = await loadOrbit()
    // The same extension, on two consoles, is two different objects.
    expect(physicalKind('duckstation', 'Game.bin')).toBe('disc')
    expect(physicalKind('mgba', 'Game.bin')).toBe('cart')
  })

  it('knows a Switch card is a cartridge and not a disc', async () => {
    const { physicalKind } = await loadOrbit()
    expect(physicalKind('ryujinx', 'Zelda.xci')).toBe('cart')
    expect(physicalKind('ryujinx', 'Mario.nsp')).toBe('cart')
  })

  it('falls back to the extension for a pack it has never heard of', async () => {
    const { physicalKind } = await loadOrbit()
    expect(physicalKind('some-new-pack', 'Game.chd')).toBe('disc')
    expect(physicalKind('some-new-pack', 'Game.sfc')).toBe('cart')
    expect(physicalKind('some-new-pack', 'Game.weird')).toBe('cart')
  })

  it('only asks for the media a game could actually have', async () => {
    const { createPhysicalMedia } = await loadOrbit()
    const list = vi.fn().mockResolvedValue(withArt('disc', 'cart-front'))
    const sdk = fakeSdk(list)
    const PhysicalMedia = createPhysicalMedia(sdk)

    const r = render(createElement(PhysicalMedia, {
      systemId: 'pcsx2', filename: 'Ico.iso', ext: 'iso', title: 'Ico', active: true,
    }))
    // A disc game takes the disc photograph, never the cartridge one — a
    // cartridge in a disc frame is a nicer-looking mistake, but a mistake.
    await waitFor(() => expect(r.container.querySelector('img')?.getAttribute('src'))
      .toContain('/media/disc'))
  })

  it('draws a cartridge shell when the game has no photograph', async () => {
    const { createPhysicalMedia } = await loadOrbit()
    const list = vi.fn().mockResolvedValue({ media: {} })
    const PhysicalMedia = createPhysicalMedia(fakeSdk(list))

    const r = render(createElement(PhysicalMedia, {
      systemId: 'mgba', filename: 'Metroid.gba', ext: 'gba', title: 'Metroid', active: true,
    }))
    await waitFor(() => expect(list).toHaveBeenCalled())
    await waitFor(() => expect(r.container.querySelector('.orbit-cart')).toBeTruthy())
    expect(r.container.querySelector('[data-kind="cart"]')).toBeTruthy()
  })

  it('never asks about a card nobody has selected', async () => {
    const { createPhysicalMedia } = await loadOrbit()
    const list = vi.fn().mockResolvedValue(withArt('cart-front'))
    const PhysicalMedia = createPhysicalMedia(fakeSdk(list))

    render(createElement(PhysicalMedia, {
      systemId: 'mgba', filename: 'Metroid.gba', ext: 'gba', title: 'Metroid', active: false,
    }))
    await settle()
    expect(list).not.toHaveBeenCalled()
  })

  it('asks nothing at all for a card passed over inside the debounce', async () => {
    const { createPhysicalMedia } = await loadOrbit()
    const list = vi.fn().mockResolvedValue(withArt('cart-front'))
    const PhysicalMedia = createPhysicalMedia(fakeSdk(list))

    const r = render(createElement(PhysicalMedia, {
      systemId: 'mgba', filename: 'Metroid.gba', ext: 'gba', title: 'Metroid', active: true,
    }))
    // Deselected before it settles: the cursor moved on, and this card owes
    // the network nothing.
    r.rerender(createElement(PhysicalMedia, {
      systemId: 'mgba', filename: 'Metroid.gba', ext: 'gba', title: 'Metroid', active: false,
    }))
    await settle()
    expect(list).not.toHaveBeenCalled()
  })
})

// ── the backdrop ─────────────────────────────────────────────────────────────

describe('the backdrop', () => {
  it('does not look anything up while the cursor is still moving', async () => {
    const { createBackdrop } = await loadOrbit()
    const list = vi.fn().mockResolvedValue(withArt('fanart-background'))
    const backdrop = createBackdrop(fakeSdk(list))

    render(createElement(backdrop.Background))
    await flush()
    // One burst: awaiting between selections would let each one settle, and
    // the test would be measuring its own pace rather than the debounce.
    await act(async () => {
      for (let i = 0; i < 12; i++) {
        backdrop.select({ kind: 'game', systemId: 'rpcs3', filename: `Game${i}.iso` })
      }
    })
    // Twelve games crossed in a quarter of a second, and only the one the
    // cursor stopped on is worth a request.
    await settle()
    expect(list.mock.calls.length).toBeLessThanOrEqual(1)
  })

  it('keeps the picture it has while an app or a collection is passed over', async () => {
    const { createBackdrop } = await loadOrbit()
    const list = vi.fn().mockResolvedValue(withArt('fanart-background'))
    const backdrop = createBackdrop(fakeSdk(list))
    const r = render(createElement(backdrop.Background))

    await act(async () => { backdrop.select({ kind: 'game', systemId: 'rpcs3', filename: 'Journey.iso' }) })
    await waitFor(() => expect(r.container.querySelector('.orbit-backdrop-current')).toBeTruthy())

    // Crossing a tile with no picture of its own, briefly, must not blank a
    // perfectly good backdrop.
    await act(async () => { backdrop.select({ kind: 'app', systemId: 'youtube' }) })
    await flush(60)
    expect(r.container.querySelector('.orbit-backdrop-current')).toBeTruthy()
  })

  it('says the same selection twice without asking twice', async () => {
    const { createBackdrop } = await loadOrbit()
    const list = vi.fn().mockResolvedValue(withArt('background'))
    const backdrop = createBackdrop(fakeSdk(list))
    render(createElement(backdrop.Background))
    await flush()

    const pick = { kind: 'game', systemId: 'rpcs3', filename: 'Journey.iso' }
    await act(async () => {
      backdrop.select({ ...pick })
      backdrop.select({ ...pick })
    })
    await settle()
    expect(list).toHaveBeenCalledTimes(1)
  })
})
