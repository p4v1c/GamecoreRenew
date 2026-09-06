/**
 * The card's cache, and the difference between "nothing" and "no answer".
 *
 * Finding 8 of the 2026-09-04 audit. `load()` swallows every exception — which
 * is right for the card, since a game nobody has scraped and a scraper that
 * timed out both leave it empty — and then wrote the empty result into a
 * module-level Map with no expiry. So one bad moment was permanent: the
 * backend restarting, or a scraper timing out once, and that game's card
 * stayed blank for the life of the page. Walking away and coming back showed
 * the same nothing, with no way to ask again. Media configured or scraped
 * afterwards could not appear either.
 *
 * An answer is cached. A failure is not.
 */
import React from 'react'
import { render, act, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const THEME = '../../../config/themes/shelf'

const flush = () => act(async () => { await new Promise(r => setTimeout(r, 0)) })

/** A fresh module each time: the cache is module state, and that is the point. */
const useDossierFor = async (api: unknown) => {
  vi.resetModules()
  const { createUseDossier } = await import(/* @vite-ignore */ `${THEME}/lib/dossier.js`)
  return createUseDossier({ ui: React, api })
}

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('a card that could not be loaded', () => {
  it('is asked for again the next time the game is looked at', async () => {
    const media = vi.fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ meta: { title: 'Recovered' }, media: {} })
    const metadata = vi.fn().mockRejectedValue(new Error('offline'))
    const useDossier = await useDossierFor({ media: { list: media }, metadata: { get: metadata } })

    const Card = () => {
      const d = useDossier('retry-system', 'retry.rom')
      return <div>{d.meta.title || 'empty'}</div>
    }

    const first = render(<Card />); await flush()
    expect(first.container.textContent).toBe('empty')
    first.unmount()

    const second = render(<Card />); await flush()
    expect(second.container.textContent).toBe('Recovered')
  })

  it('does not ask twice for a lookup already in flight', async () => {
    let answer!: (v: unknown) => void
    const media = vi.fn().mockImplementation(() => new Promise(r => { answer = r }))
    const metadata = vi.fn().mockResolvedValue({ found: false })
    const useDossier = await useDossierFor({ media: { list: media }, metadata: { get: metadata } })

    const Card = () => {
      const d = useDossier('busy-system', 'busy.rom')
      return <div>{d.meta.title || 'empty'}</div>
    }

    const first = render(<Card />); await flush()
    first.unmount()
    const second = render(<Card />); await flush()
    expect(media).toHaveBeenCalledTimes(1)

    await act(async () => { answer({ meta: { title: 'Only once' }, media: {} }) })
    expect(second.container.textContent).toBe('Only once')
  })
})

describe('a card that genuinely has nothing on it', () => {
  it('is remembered, and asked for only once', async () => {
    // `found: false` is an answer: this game is not in any catalogue. Asking
    // again on every pass along the shelf would be a request per step for a
    // question already settled.
    const media = vi.fn().mockResolvedValue({ meta: {}, media: {} })
    const metadata = vi.fn().mockResolvedValue({ found: false })
    const useDossier = await useDossierFor({ media: { list: media }, metadata: { get: metadata } })

    const Card = () => {
      const d = useDossier('empty-system', 'unknown.rom')
      return <div>{d.meta.title || 'empty'}</div>
    }

    const first = render(<Card />); await flush()
    expect(first.container.textContent).toBe('empty')
    first.unmount()

    const second = render(<Card />); await flush()
    expect(second.container.textContent).toBe('empty')
    expect(media).toHaveBeenCalledTimes(1)
    expect(metadata).toHaveBeenCalledTimes(1)
  })
})
