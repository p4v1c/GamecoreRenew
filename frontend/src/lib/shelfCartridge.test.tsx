/**
 * Shelf's physical media: what a game is drawn as, and which photograph counts.
 *
 * The card draws the object you would be holding, and when a game has no
 * photograph of its media it builds one — a shell in CSS with the jacket set
 * into its label window. Two things decide whether that reads as the game or
 * as a bug, and both were wrong:
 *
 *   · **Which shell.** It was read off the file extension alone, and a
 *     Switch card dump is `.xci`/`.nsp` — which the disc list claimed. Every
 *     Switch game in the collection was drawn as an optical disc. Meanwhile
 *     `.bin` is a PlayStation track *and* a Mega Drive ROM, and no extension
 *     rule can tell those apart. The platform can.
 *   · **Which photograph.** The card asked for `['cart-front','cart-3d','disc']`
 *     whatever the game was, so a disc game that happened to carry a cartridge
 *     photograph got a cartridge, and vice versa.
 *
 * How any of it LOOKS is the owner's to judge and is claimed nowhere here.
 */
import React, { createElement } from 'react'
import { render, cleanup, act } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import htm from 'htm'

const THEME = '../../../config/themes/shelf'

const ui = { html: htm.bind(React.createElement), React, useState: React.useState, useEffect: React.useEffect }

const sdk = {
  ui,
  api: {
    media: {
      url: (systemId: string, filename: string, type: string) =>
        `/api/media/${systemId}/${filename}/media/${type}`,
    },
  },
}

/** A fresh module each time — `dossier.js` keeps a module-level cache. */
async function loadShelf() {
  vi.resetModules()
  const [cartridge, dossier] = await Promise.all([
    import(/* @vite-ignore */ `${THEME}/views/cartridge.js`),
    import(/* @vite-ignore */ `${THEME}/lib/dossier.js`),
  ])
  return { ...cartridge, ...dossier }
}

const image = (...types: string[]) =>
  Object.fromEntries(types.map(t => [t, { kind: 'image' }]))

afterEach(() => { cleanup(); vi.restoreAllMocks() })

// ── which shell ──────────────────────────────────────────────────────────────

describe('what the game shipped on', () => {
  it('draws a Switch card as a cartridge, not a disc', async () => {
    // The defect, exactly: `xci` and `nsp` sat in the disc list, so every
    // Switch game in the collection was drawn as an optical disc.
    const { shellFor } = await loadShelf()
    expect(shellFor('.xci', 'ryujinx')).toBe('cart')
    expect(shellFor('.nsp', 'ryujinx')).toBe('cart')
  })

  it('draws an ISO or a CHD as a disc', async () => {
    const { shellFor } = await loadShelf()
    expect(shellFor('.iso', 'pcsx2')).toBe('disc')
    expect(shellFor('.chd', 'duckstation')).toBe('disc')
    expect(shellFor('.cue', 'duckstation')).toBe('disc')
  })

  it('reads .bin off the platform, because the extension cannot say', async () => {
    // A PlayStation track and a Mega Drive ROM are both `.bin`. Only the
    // console the game is filed under can tell them apart.
    const { shellFor } = await loadShelf()
    expect(shellFor('.bin', 'duckstation')).toBe('disc')
    expect(shellFor('.bin', 'mgba')).toBe('cart')
  })

  it('lets the platform overrule the extension both ways', async () => {
    const { shellFor } = await loadShelf()
    // A handheld emulator's game is a cartridge whatever the container says.
    expect(shellFor('.iso', 'melonds')).toBe('cart')
    // And a disc console's is a disc.
    expect(shellFor('.zip', 'rpcs3')).toBe('disc')
  })

  it('still answers for a pack it has never heard of', async () => {
    // Community packs are the reason the extension fallback stays.
    const { shellFor } = await loadShelf()
    expect(shellFor('.chd', 'some-new-pack')).toBe('disc')
    expect(shellFor('.sfc', 'some-new-pack')).toBe('cart')
  })

  it('falls back to a cartridge for a format nobody recognises', async () => {
    const { shellFor } = await loadShelf()
    expect(shellFor('.wat', '')).toBe('cart')
    expect(shellFor(undefined, undefined)).toBe('cart')
  })
})

// ── which photograph ─────────────────────────────────────────────────────────

describe('the photograph a game is allowed to use', () => {
  const draw = async (game: Record<string, unknown>, systemId: string,
                      media: Record<string, unknown>) => {
    const { createCartridge } = await loadShelf()
    const Cartridge = createCartridge(sdk)
    return render(createElement(Cartridge, { systemId, game, media }))
  }

  it('gives a cartridge game its cartridge photograph', async () => {
    const r = await draw({ filename: 'Zelda.xci', ext: '.xci' }, 'ryujinx',
      image('cart-front'))
    const img = r.container.querySelector('img')
    expect(img?.getAttribute('src')).toContain('/media/cart-front')
    expect(r.container.querySelector('[data-medium="cart"]')).toBeTruthy()
  })

  it('gives a disc game its disc photograph', async () => {
    const r = await draw({ filename: 'Ico.iso', ext: '.iso' }, 'pcsx2', image('disc'))
    expect(r.container.querySelector('img')?.getAttribute('src')).toContain('/media/disc')
  })

  it('does not put a disc photograph on a cartridge game', async () => {
    // A jacket in a cartridge frame looks like a bug; a *disc* in one is the
    // same mistake with more confidence behind it. The built shell is right.
    const r = await draw({ filename: 'Zelda.xci', ext: '.xci' }, 'ryujinx', image('disc'))
    expect(r.container.querySelector('img')).toBeNull()
    expect(r.container.querySelector('.cz-cart')).toBeTruthy()
  })

  it('does not put a cartridge photograph on a disc game', async () => {
    const r = await draw({ filename: 'Ico.iso', ext: '.iso' }, 'pcsx2',
      image('cart-front', 'cart-3d'))
    expect(r.container.querySelector('img')).toBeNull()
    expect(r.container.querySelector('.cz-disc')).toBeTruthy()
  })

  it('builds the shell when the game has no photograph at all', async () => {
    // Most games in most collections have none, so this is the normal case
    // and not the fallback.
    const r = await draw({ filename: 'Metroid.gba', ext: '.gba' }, 'mgba', {})
    expect(r.container.querySelector('.cz-cart')).toBeTruthy()
    expect(r.container.querySelector('.cz-cart-art')).toBeTruthy()
  })

  it('draws nothing at all when there is no game', async () => {
    const { createCartridge } = await loadShelf()
    const Cartridge = createCartridge(sdk)
    const r = render(createElement(Cartridge, { systemId: 'mgba', game: null, media: {} }))
    expect(r.container.innerHTML).toBe('')
  })
})

// ── what counts as a picture ─────────────────────────────────────────────────

describe('pick', () => {
  it('refuses a media entry that is not an image', async () => {
    // A video or a PDF manual is a media entry too, and putting one in an
    // <img> is a broken picture rather than a missing one.
    const { pick } = await loadShelf()
    const chosen = pick(sdk, 'pcsx2', 'Ico.iso',
      { disc: { kind: 'video' } }, ['disc'])
    expect(chosen).toBeNull()
  })

  it('still accepts an index from before entries said what they were', async () => {
    // Legacy indices carry no `kind`. Refusing those would blank artwork that
    // has been on screen for as long as the box has existed.
    const { pick } = await loadShelf()
    const chosen = pick(sdk, 'pcsx2', 'Ico.iso', { disc: {} }, ['disc'])
    expect(chosen).toContain('/media/disc')
  })

  it('takes the first type the game actually has, in the order asked', async () => {
    const { pick } = await loadShelf()
    const chosen = pick(sdk, 'ryujinx', 'Zelda.xci',
      image('cart-3d'), ['cart-front', 'cart-3d'])
    expect(chosen).toContain('/media/cart-3d')
  })

  it('answers null rather than guessing when the game has none of them', async () => {
    const { pick } = await loadShelf()
    expect(pick(sdk, 'mgba', 'Metroid.gba', image('box-2d'), ['cart-front'])).toBeNull()
    expect(pick(sdk, 'mgba', 'Metroid.gba', undefined, ['cart-front'])).toBeNull()
  })
})

// ── the cache, and what belongs in it ────────────────────────────────────────

describe('the dossier cache', () => {
  const useDossierFor = async (api: unknown) => {
    vi.resetModules()
    const { createUseDossier } = await import(/* @vite-ignore */ `${THEME}/lib/dossier.js`)
    return createUseDossier({ ui: React, api })
  }

  const flush = () => new Promise(r => setTimeout(r, 0))

  it('keeps a media answer even when the metadata tier is unreachable', async () => {
    // The two tiers fail independently. Throwing away a media answer we
    // already hold because the *optional* metadata fallback timed out means
    // asking for artwork again that the box has already been told about.
    const list = vi.fn().mockResolvedValue({ media: image('cart-front'), meta: {} })
    const get = vi.fn().mockRejectedValue(new Error('scraper down'))
    const useDossier = await useDossierFor({ media: { list }, metadata: { get } })

    const Card = () => {
      const d = useDossier('ryujinx', 'Zelda.xci')
      return createElement('div', null, Object.keys(d.media).join(',') || 'none')
    }

    const first = render(createElement(Card))
    await act(async () => { await flush() })
    expect(first.container.textContent).toBe('cart-front')
    first.unmount()

    // Cached: the second look costs nothing.
    const second = render(createElement(Card))
    await act(async () => { await flush() })
    expect(second.container.textContent).toBe('cart-front')
    expect(list).toHaveBeenCalledTimes(1)
  })

  it('leaves a failed media lookup retryable', async () => {
    // A backend restarting, or a scraper that timed out once, must not blank a
    // game for the life of the page.
    const list = vi.fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ media: image('disc'), meta: { title: 'Ico' } })
    const get = vi.fn().mockResolvedValue({ found: false })
    const useDossier = await useDossierFor({ media: { list }, metadata: { get } })

    const Card = () => {
      const d = useDossier('pcsx2', 'Ico.iso')
      return createElement('div', null, Object.keys(d.media).join(',') || 'none')
    }

    const first = render(createElement(Card))
    await act(async () => { await flush() })
    expect(first.container.textContent).toBe('none')
    first.unmount()

    const second = render(createElement(Card))
    await act(async () => { await flush() })
    expect(second.container.textContent).toBe('disc')
    expect(list).toHaveBeenCalledTimes(2)
  })

  it('asks once for a game two cards are looking at', async () => {
    let answer!: (v: unknown) => void
    const list = vi.fn().mockImplementation(() => new Promise(r => { answer = r }))
    const get = vi.fn().mockResolvedValue({ found: false })
    const useDossier = await useDossierFor({ media: { list }, metadata: { get } })

    const Card = () => {
      const d = useDossier('rpcs3', 'Journey.iso')
      return createElement('div', null, d.loading ? 'loading' : 'ready')
    }

    render(createElement(Card))
    render(createElement(Card))
    await act(async () => {
      answer({ media: image('disc'), meta: {} })
      await flush()
    })
    expect(list).toHaveBeenCalledTimes(1)
  })
})
