/**
 * `useStoreSearch` — the one implementation, tested on its own.
 *
 * The same reason `catalog.test.tsx` beside it exists: the point of a module
 * is that the second screen to want a game search cannot start a second copy,
 * and a module that could only be exercised through `StoreScreen` would be one
 * refactor away from being inlined back into it.
 *
 * `StoreScreen`'s own file tests its cursor and its markup. What is here is
 * everything neither it nor a theme may decide again — which console a search
 * is scoped to, what a failure leaves on screen, and that asking for a result
 * downloads nothing.
 */
import { render, act, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api, type CatalogEntry, type StoreSearchAnswer, type StoreSearchResult } from '../api'
import { useStoreSearch, formatSize, SEARCH_FAILED, type StoreSearchState } from './storeSearch'

const pack = (id: string, extra: Partial<CatalogEntry> = {}): CatalogEntry => ({
  id, kind: 'emulator', label: id, platform: id, family: '', color: '#6a5acd',
  logo: null, emulatorName: id, description: '', origin: 'shipped',
  installed: true, restricted: [], ...extra,
})

const NES = pack('nes', { label: 'NES' })
const MAME = pack('mame', { label: 'Arcade' })

const row = (id: string, extra: Partial<StoreSearchResult> = {}): StoreSearchResult => ({
  id, title: id, filename: `${id}.zip`, format: 'zip', size: 1024,
  systemId: 'nes', provider: 'demo', source: `demo://nes/${id}`,
  region: 'USA', languages: ['en'], ...extra,
})

const ANSWER: StoreSearchAnswer = {
  system: 'nes', label: 'NES', romsDir: 'emu/nes', provider: 'demo',
  live: false, query: 'zelda', results: [row('a'), row('b')],
}

const flush = () => act(async () => { await new Promise(r => setTimeout(r, 0)) })

/** Mount the hook and hand back a live read of what it returns. */
async function mount() {
  let seen!: StoreSearchState
  const Probe = () => { seen = useStoreSearch(); return null }
  render(<Probe />)
  await flush()
  return () => seen
}

beforeEach(() => {
  vi.spyOn(api.store, 'provider').mockResolvedValue({
    name: 'demo', label: 'Demo results', live: false, systemFirst: true })
  vi.spyOn(api.store, 'search').mockResolvedValue(ANSWER)
})

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('the console comes first', () => {
  it('searches nothing until one is chosen', async () => {
    // Not a menu preference: the ingestion class of a download is a property
    // of the pair (system, incoming format) and the directory it lands in
    // belongs to the system, so a result found without a console attached
    // could be neither placed nor classified — matrix §0, §1.3.
    const s = await mount()
    expect(s().system).toBeNull()
    await act(async () => { await s().run('zelda') })
    expect(api.store.search).not.toHaveBeenCalled()
  })

  it('sends the console with every query', async () => {
    const s = await mount()
    act(() => s().choose(NES))
    await act(async () => { await s().run('zelda') })
    expect(api.store.search).toHaveBeenCalledWith('nes', 'zelda')
    expect(s().results.map(r => r.id)).toEqual(['a', 'b'])
    expect(s().romsDir).toBe('emu/nes')
  })

  it('drops the last console’s results when another is chosen', async () => {
    // They were answers about a different machine. Leaving them up would show
    // NES results under an arcade heading.
    const s = await mount()
    act(() => s().choose(NES))
    await act(async () => { await s().run('zelda') })
    expect(s().results).toHaveLength(2)

    act(() => s().choose(MAME))
    expect(s().system?.id).toBe('mame')
    expect(s().results).toEqual([])
    expect(s().query).toBe('')
    expect(s().answered).toBe(false)
  })

  it('steps back out of the console entirely', async () => {
    const s = await mount()
    act(() => s().choose(NES))
    await act(async () => { await s().run('zelda') })
    act(() => s().leave())
    expect(s().system).toBeNull()
    expect(s().results).toEqual([])
  })

  it('ignores an empty query rather than asking for everything', async () => {
    const s = await mount()
    act(() => s().choose(NES))
    await act(async () => { await s().run('   ') })
    expect(api.store.search).not.toHaveBeenCalled()
  })

  it('trims what the on-screen keyboard hands it', async () => {
    const s = await mount()
    act(() => s().choose(NES))
    await act(async () => { await s().run('  zelda  ') })
    expect(api.store.search).toHaveBeenCalledWith('nes', 'zelda')
    expect(s().query).toBe('zelda')
  })
})

describe('a failure, which is not the same as nothing found', () => {
  it('says the search failed and keeps no rows from it', async () => {
    const s = await mount()
    act(() => s().choose(NES))
    vi.mocked(api.store.search).mockRejectedValueOnce(new Error('502'))
    await act(async () => { await s().run('zelda') })

    expect(s().error).toBe(SEARCH_FAILED)
    expect(s().results).toEqual([])
    // `useCatalog` keeps its list through a failed re-read and this does not,
    // and the difference is what the rows are: a catalogue the box maintains
    // against the answer to one request. Keeping them would leave the last
    // query's results sitting under the new query's heading.
    expect(s().answered).toBe(false)
    expect(s().loading).toBe(false)
  })

  it('leaves no error behind when a search answers nothing', async () => {
    const s = await mount()
    act(() => s().choose(NES))
    vi.mocked(api.store.search).mockResolvedValueOnce({ ...ANSWER, results: [] })
    await act(async () => { await s().run('zelda') })

    expect(s().error).toBe('')
    expect(s().answered).toBe(true)
    expect(s().results).toEqual([])
  })

  it('clears the last failure when the next search starts', async () => {
    const s = await mount()
    act(() => s().choose(NES))
    vi.mocked(api.store.search).mockRejectedValueOnce(new Error('502'))
    await act(async () => { await s().run('zelda') })
    expect(s().error).toBe(SEARCH_FAILED)

    await act(async () => { await s().run('mario') })
    expect(s().error).toBe('')
    expect(s().results).toHaveLength(2)
  })
})

describe('answers arriving out of order', () => {
  it('keeps the one that was asked for last', async () => {
    // Three requests are never cancellable and a console with a common title
    // answers slower than one with none. The library carries the same guard.
    const s = await mount()
    act(() => s().choose(NES))

    let releaseSlow!: (a: StoreSearchAnswer) => void
    vi.mocked(api.store.search)
      .mockImplementationOnce(() => new Promise(res => { releaseSlow = res }))
      .mockResolvedValueOnce({ ...ANSWER, query: 'mario', results: [row('fast')] })

    let slow!: Promise<void>
    act(() => { slow = s().run('zelda') })
    await act(async () => { await s().run('mario') })
    expect(s().results.map(r => r.id)).toEqual(['fast'])

    await act(async () => { releaseSlow(ANSWER); await slow })
    expect(s().results.map(r => r.id)).toEqual(['fast'])
  })

  it('drops an answer for a console the player has already left', async () => {
    const s = await mount()
    act(() => s().choose(NES))
    let release!: (a: StoreSearchAnswer) => void
    vi.mocked(api.store.search).mockImplementationOnce(
      () => new Promise(res => { release = res }))

    let pending!: Promise<void>
    act(() => { pending = s().run('zelda') })
    act(() => s().leave())
    await act(async () => { release(ANSWER); await pending })

    expect(s().system).toBeNull()
    expect(s().results).toEqual([])
  })
})

describe('asking for a result', () => {
  it('records the choice and downloads nothing', async () => {
    // The whole of what asking means at this step. A call that answered
    // "accepted" while nothing downloaded would be the button that does
    // nothing, and a queue behind it is a later step with its own seam.
    const s = await mount()
    act(() => s().choose(NES))
    await act(async () => { await s().run('zelda') })

    act(() => s().ask(s().results[1]))
    expect(s().asked?.id).toBe('b')
    // A tripwire, on purpose: the client has no verb that downloads anything,
    // so there is nothing `ask` could have called. The step that adds
    // acquisition updates this line deliberately rather than discovering that
    // a queue grew here by accident.
    expect(Object.keys(api.store)).toEqual(['provider', 'search'])

    act(() => s().unask())
    expect(s().asked).toBeNull()
  })

  it('puts it down when the console changes under it', async () => {
    const s = await mount()
    act(() => s().choose(NES))
    await act(async () => { await s().run('zelda') })
    act(() => s().ask(s().results[0]))
    act(() => s().choose(MAME))
    expect(s().asked).toBeNull()
  })
})

describe('saying where the rows came from', () => {
  it('reports the provider as not live, and does not assume otherwise', async () => {
    const s = await mount()
    expect(s().live).toBe(false)
    expect(s().providerLabel).toBe('Demo results')
  })

  it('stays not-live when the provider cannot be asked', async () => {
    // The cautious answer. A tab that assumed real sources because one request
    // failed would be the dishonest half of this whole feature.
    vi.mocked(api.store.provider).mockRejectedValue(new Error('offline'))
    const s = await mount()
    expect(s().live).toBe(false)
  })

  it('takes the answer’s own word for it over the one asked on mount', async () => {
    const s = await mount()
    act(() => s().choose(NES))
    vi.mocked(api.store.search).mockResolvedValueOnce({ ...ANSWER, live: true })
    await act(async () => { await s().run('zelda') })
    expect(s().live).toBe(true)
  })
})

describe('formatSize', () => {
  it('reads at two metres', () => {
    expect(formatSize(0)).toBe('—')
    expect(formatSize(512)).toBe('512 B')
    expect(formatSize(1024)).toBe('1.0 KB')
    expect(formatSize(1536)).toBe('1.5 KB')
    expect(formatSize(45 * 1024 * 1024)).toBe('45 MB')
    expect(formatSize(3 * 1024 ** 3)).toBe('3.0 GB')
  })

  it('says nothing rather than zero when the source does not say', () => {
    // `0` means "not stated", not "an empty file" — see the endpoint.
    expect(formatSize(0)).toBe('—')
  })
})
