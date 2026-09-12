/**
 * `useCatalog` — the one implementation, tested on its own.
 *
 * It has to be testable alone, because the point of it is that three screens
 * stop deciding these things for themselves: the Store's Consoles tab, the
 * applications page in the settings rail, and the applications page in the
 * fallback modal. Before it there were three hand-written copies of this
 * sequence and they disagreed about whether removing asks twice, about whether
 * anyone asks `GET /catalog/busy`, and about where an application belongs.
 *
 * Each screen's own file still tests its cursor and its markup. What is here is
 * everything none of them may decide again.
 */
import { render, act, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** The WebSocket bus, replaced by something this file can fire by hand. */
const listeners = vi.hoisted(() => new Map<string, Set<(data: unknown) => void>>())
vi.mock('../hooks/useWebSocket', async (orig) => ({
  ...await orig<Record<string, unknown>>(),
  onWsEvent: (name: string, fn: (d: unknown) => void) => {
    if (!listeners.has(name)) listeners.set(name, new Set())
    listeners.get(name)!.add(fn)
    return () => listeners.get(name)?.delete(fn)
  },
}))

import { api, type CatalogEntry } from '../api'
import { useCatalog, CATALOG_FAILED, type CatalogSection, type CatalogDone } from './catalog'

const pack = (id: string, kind: CatalogEntry['kind'], extra: Partial<CatalogEntry> = {}): CatalogEntry => ({
  id, kind, label: id, platform: id, family: '', color: '#6a5acd', logo: null,
  emulatorName: id, description: '', origin: 'shipped', installed: false,
  restricted: [], ...extra,
})

const CATALOGUE: CatalogEntry[] = [
  pack('dolphin', 'emulator', { installed: true, family: 'Nintendo' }),
  pack('melonds', 'emulator'),
  pack('steam', 'app', { installed: true }),
  pack('youtube', 'app'),
]

const flush = () => act(async () => { await new Promise(r => setTimeout(r, 0)) })
const emit = (name: string, data: unknown) =>
  act(async () => {
    listeners.get(name)?.forEach(fn => fn(data))
    await new Promise(r => setTimeout(r, 0))
  })

/** Mount the hook and hand back a live read of what it returns. */
async function mount(kind: CatalogEntry['kind'], onDone?: (d: CatalogDone) => void) {
  let seen!: CatalogSection
  const Probe = () => { seen = useCatalog({ kind, onDone }); return null }
  render(<Probe />)
  await flush()
  return () => seen
}

beforeEach(() => {
  vi.spyOn(api.catalog, 'list').mockResolvedValue(CATALOGUE)
  vi.spyOn(api.catalog, 'busy').mockResolvedValue({ busy: false })
  vi.spyOn(api.catalog, 'install').mockResolvedValue({} as never)
  vi.spyOn(api.catalog, 'remove').mockResolvedValue({} as never)
  vi.spyOn(api.catalog, 'reconfigure').mockResolvedValue({} as never)
})

afterEach(() => { cleanup(); vi.restoreAllMocks(); listeners.clear() })

describe('which half of the catalogue a screen gets', () => {
  it('splits on `kind`, which is the pack’s own word for what it is', async () => {
    // Not on `family`: no application pack declares one, which is how one of
    // the copies this replaces came to file Steam and YouTube under "Other"
    // while the other filed them under "Applications".
    const consoles = await mount('emulator')
    expect(consoles().rows?.map(r => r.id)).toEqual(['dolphin', 'melonds'])

    cleanup()
    const apps = await mount('app')
    expect(apps().rows?.map(r => r.id)).toEqual(['steam', 'youtube'])
    // …and the whole list stays reachable, for a count that spans both screens.
    expect(apps().all).toHaveLength(4)
  })

  it('says nothing rather than nothing-found before the first answer', async () => {
    // `null` is "not asked yet" and `[]` is "asked, and there are none". A
    // screen that could not tell them apart would greet every boot with its
    // empty state for as long as the request took.
    let seen!: CatalogSection
    const Probe = () => { seen = useCatalog({ kind: 'app' }); return null }
    render(<Probe />)
    expect(seen.rows).toBeNull()
    await flush()
    expect(seen.rows).toEqual([CATALOGUE[2], CATALOGUE[3]])
  })

  it('keeps the rows it had when a re-read fails', async () => {
    const at = await mount('app')
    vi.mocked(api.catalog.list).mockRejectedValue(new Error('no box'))
    await act(async () => { await at().load() })
    expect(at().loadFailed).toBe(true)
    // A screen that dropped every row because one poll failed would read as a
    // box with nothing on it.
    expect(at().rows).toHaveLength(2)
  })
})

describe('removing, which is the one thing here that cannot be undone', () => {
  it('arms on the first press and acts on the second', async () => {
    const at = await mount('app')
    const steam = at().rows![0]

    await act(async () => { await at().act(steam) })
    expect(at().armedId).toBe('steam')
    expect(api.catalog.remove).not.toHaveBeenCalled()

    await act(async () => { await at().act(steam) })
    expect(api.catalog.remove).toHaveBeenCalledWith('steam')
    expect(at().armedId).toBe('')
  })

  it('disarms when the cursor steps away', async () => {
    const at = await mount('app')
    await act(async () => { await at().act(at().rows![0]) })
    expect(at().armedId).toBe('steam')
    act(() => at().disarm())
    expect(at().armedId).toBe('')
  })

  it('arms per pack, so a confirmation cannot land on a neighbour', async () => {
    const at = await mount('emulator')
    await act(async () => { await at().act(at().rows![0]) })   // dolphin, installed
    expect(at().armedId).toBe('dolphin')
    // melonDS is not installed, so this is an install and not a confirmation of
    // the armed removal above.
    await act(async () => { await at().act(at().rows![1]) })
    expect(api.catalog.install).toHaveBeenCalledWith('melonds')
    expect(api.catalog.remove).not.toHaveBeenCalled()
  })

  it('installs on one press, because installing is additive', async () => {
    const at = await mount('app')
    await act(async () => { await at().act(at().rows![1]) })   // youtube
    expect(api.catalog.install).toHaveBeenCalledWith('youtube')
    expect(at().workingId).toBe('youtube')
  })
})

describe('one action at a time, which the backend enforces with a 409', () => {
  it('refuses a second while one of ours is running', async () => {
    const at = await mount('emulator')
    await act(async () => { await at().act(at().rows![1]) })   // melonds, install
    expect(at().busy).toBe(true)

    await act(async () => { await at().act(at().rows![0]) })
    expect(api.catalog.remove).not.toHaveBeenCalled()
    expect(at().armedId).toBe('')                             // not even armed
  })

  it('starts held when the box says it already is', async () => {
    // Only one of the three copies asked this, and a screen that never asks
    // offers a button that cannot work: the install it starts is answered 409
    // and the row sits on "Working…" until somebody leaves the page.
    vi.mocked(api.catalog.busy).mockResolvedValue({ busy: true })
    const at = await mount('app')
    expect(at().busy).toBe(true)
    expect(at().workingId).toBe('')     // held, but not by anything of ours
    await act(async () => { await at().act(at().rows![1]) })
    expect(api.catalog.install).not.toHaveBeenCalled()
  })

  it('learns about a run another screen started, from its output', async () => {
    // There is no `catalog:start` event, and the settings modal opens over the
    // Store and leaves it mounted — so both are listening and only one of them
    // took the lock.
    const at = await mount('emulator')
    expect(at().busy).toBe(false)
    await emit('catalog:log', { line: 'Installing…' })
    expect(at().busy).toBe(true)
    expect(at().workingId).toBe('')
    await emit('catalog:done', { success: true })
    expect(at().busy).toBe(false)
  })

  it('releases the screen when the call never started', async () => {
    // Nothing is coming back on the socket to release it, so the rejection has
    // to — otherwise the list stays held for the life of the screen.
    vi.mocked(api.catalog.install).mockRejectedValue(new Error('409 busy'))
    const at = await mount('app')
    await act(async () => { await at().act(at().rows![1]) })
    expect(at().workingId).toBe('')
    expect(at().busy).toBe(false)
    expect(at().actionError).toContain('409')
  })
})

describe('what `catalog:done` closes', () => {
  it('re-reads on success, and hands the screen its cursor back first', async () => {
    const order: string[] = []
    vi.mocked(api.catalog.list).mockImplementation(async () => {
      order.push('read'); return CATALOGUE
    })
    const at = await mount('app', () => order.push('onDone'))
    order.length = 0

    await emit('catalog:done', { action: 'install', id: 'youtube', success: true })
    // `onDone` before the re-read: it is where a screen records what its cursor
    // was pointing at, and by the time the new rows arrive that row is at a
    // different index.
    expect(order).toEqual(['onDone', 'read'])
    expect(at().workingId).toBe('')
    expect(at().actionError).toBe('')
  })

  it('re-reads after a failure too, and says so', async () => {
    // `_run_cli` kills the CLI at `_CLI_TIMEOUT` and reports `success: false`
    // after however much of the work it had already done, and `installed` is
    // read from the systems.json that work writes. Skipping the re-read leaves
    // every screen saying "not installed" about a half-installed pack.
    const at = await mount('app')
    vi.mocked(api.catalog.list).mockClear()
    await emit('catalog:done', { action: 'install', id: 'youtube', success: false })
    expect(api.catalog.list).toHaveBeenCalled()
    expect(at().actionError).toBe(CATALOG_FAILED)
    expect(at().busy).toBe(false)
  })

  it('keeps the output of the run that is on screen, and only that one', async () => {
    const at = await mount('app')
    await act(async () => { await at().act(at().rows![1]) })   // youtube
    await emit('catalog:log', { line: 'one' })
    await emit('catalog:log', { line: 'two' })
    expect(at().log).toEqual(['one', 'two'])
    // Ours, so it is not mistaken for another screen's run.
    expect(at().workingId).toBe('youtube')

    // The next run starts from a blank pane: its predecessor's output under a
    // new "Working…" reads as progress that has already happened.
    await emit('catalog:done', { id: 'youtube', success: true })
    await act(async () => { await at().act(at().rows![1]) })
    expect(at().log).toEqual([])
  })
})

describe('reconfigure, the third verb', () => {
  it('re-runs the configuration of something that is installed', async () => {
    const at = await mount('emulator')
    await act(async () => { await at().reconfigure(at().rows![0]) })
    expect(api.catalog.reconfigure).toHaveBeenCalledWith('dolphin')
  })

  it('does nothing to a pack that is not on the box', async () => {
    // There is nothing to reconfigure, and the route would fail on its own
    // terms rather than say so.
    const at = await mount('emulator')
    await act(async () => { await at().reconfigure(at().rows![1]) })
    expect(api.catalog.reconfigure).not.toHaveBeenCalled()
  })

  it('asks once — it is not destructive, so it does not arm', async () => {
    const at = await mount('emulator')
    await act(async () => { await at().reconfigure(at().rows![0]) })
    expect(at().armedId).toBe('')
    expect(at().workingId).toBe('dolphin')
  })
})
