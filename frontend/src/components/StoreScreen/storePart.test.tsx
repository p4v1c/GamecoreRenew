/**
 * The Store part's contract — the guarantee that no theme was broken by it.
 *
 * The Store is a destination and not a settings page, and that decision is what
 * this file is really pinning. The three shipped themes all compose
 * `sdk.defaults.Shell` with parts and none of them renders a tree of its own,
 * so a part with a working default reaches every one of them without a line of
 * any theme changing. Had the Store gone in as a settings page instead, it
 * would have needed an entry in each theme's own menu — which is exactly how
 * `catalog`, `bios` and `storage` each shipped as a page that existed, a route
 * that existed, and nothing able to open them.
 *
 * So: a theme that passes no `storeView` gets the core's own and it renders; a
 * theme that passes one gets its own, with the host's data and callbacks in its
 * props and the navigation still on the host's side of the line.
 */
import { render, act, cleanup, fireEvent } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** The WebSocket bus, replaced by something this file can fire by hand. The
 *  rest of the module is kept: the shell's own tree imports `launchSession`
 *  from it, and a mock that dropped it would fail at import. */
const listeners = vi.hoisted(() => new Map<string, Set<(data: unknown) => void>>())
vi.mock('../../hooks/useWebSocket', async (orig) => ({
  ...await orig<Record<string, unknown>>(),
  onWsEvent: (name: string, fn: (d: unknown) => void) => {
    if (!listeners.has(name)) listeners.set(name, new Set())
    listeners.get(name)!.add(fn)
    return () => listeners.get(name)?.delete(fn)
  },
}))

import DefaultShell from '../DefaultShell'
import StoreScreen from './index'
import { useStore } from '../../store'
import { api, type CatalogEntry } from '../../api'
import type { StoreViewProps } from './types'

const pack = (id: string, label: string, extra: Partial<CatalogEntry> = {}): CatalogEntry => ({
  id, label, kind: 'emulator', platform: label, family: '', color: '#6a5acd',
  logo: null, emulatorName: `${label} emulator`, description: '', origin: 'shipped',
  installed: false, restricted: [], ...extra,
})

/** Enough to fill two pages of the 4 × 3 grid, plus the applications that must
 *  not appear on the Consoles tab. */
const CATALOGUE: CatalogEntry[] = [
  ...Array.from({ length: 14 }, (_, i) =>
    pack(`sys${String(i).padStart(2, '0')}`, `System ${String(i).padStart(2, '0')}`,
         { installed: i < 3 })),
  pack('steam', 'Steam', { kind: 'app' }),
  pack('youtube', 'YouTube', { kind: 'app' }),
]

const flush = () => act(async () => { await new Promise(r => setTimeout(r, 0)) })
// The handler reloads, so the state lands a microtask later — inside this act
// rather than after it, which is what keeps React from warning about it.
const emit = (name: string, data: unknown) =>
  act(async () => {
    listeners.get(name)?.forEach(fn => fn(data))
    await new Promise(r => setTimeout(r, 0))
  })
const press = (event: string) =>
  act(() => { window.dispatchEvent(new CustomEvent(event)) })

beforeEach(() => {
  // The two screens mounted beside this one fetch on mount; only the catalogue
  // is this file's subject, so the rest answers empty rather than reaching out.
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200, statusText: 'OK', json: async () => [],
  })))
  vi.spyOn(api.catalog, 'list').mockResolvedValue(CATALOGUE)
  useStore.setState({
    screen: 'store', selectedSystemId: null, modalDepth: 0, sessionGameKey: null,
    gridFocusIdx: 0, gridPage: 0,
  })
})

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); listeners.clear() })

describe('the storeView part', () => {
  it('renders the core default when a theme passes none', async () => {
    // Exactly what Orbit, Shelf and Summer do today: compose the Shell with the
    // parts they have and say nothing about a Store they have never heard of.
    const r = render(<DefaultShell homeView={() => null} libraryView={() => null} />)
    await flush()
    expect(r.container.textContent).toContain('System 00')
    expect(r.container.textContent).toContain('Games')
  })

  it('renders the theme’s own when one is passed', async () => {
    const Themed = (p: StoreViewProps) =>
      <div data-testid="themed">{p.pageItems.map(c => c.label).join(',')}</div>
    const r = render(
      <DefaultShell homeView={() => null} libraryView={() => null} storeView={Themed} />)
    await flush()
    expect(r.getByTestId('themed').textContent).toContain('System 00')
    // …and the core's markup is gone rather than drawn underneath it.
    expect(r.container.textContent).not.toContain('NOT INSTALLED')
  })

  it('hands the view the data and the callbacks, and keeps the navigation', async () => {
    let seen!: StoreViewProps
    const Probe = (p: StoreViewProps) => { seen = p; return null }
    render(<StoreScreen view={Probe} />)
    await flush()

    // Only the emulators, A–Z, paged by the host.
    expect(seen.consoles).toHaveLength(14)
    expect(seen.consoles.map(c => c.id)).not.toContain('steam')
    expect(seen.pageItems).toHaveLength(seen.perPage)
    expect(seen.pageCount).toBe(2)
    expect(seen.installedCount).toBe(3)
    expect(seen.tabs).toEqual(['consoles', 'games'])
    expect(seen.gamesReady).toBe(false)

    // The callbacks are the view's only reach into any of it.
    act(() => seen.onFocus(4))
    expect(seen.focusIdx).toBe(4)
    act(() => seen.onTab('games'))
    expect(seen.tab).toBe('games')
  })
})

describe('the navigation the host keeps', () => {
  it('walks the grid and turns the page at the edge', async () => {
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()

    press('gp:dpad-right')
    expect(seen.focusIdx).toBe(1)
    press('gp:dpad-down')
    expect(seen.focusIdx).toBe(5)

    // Off the right of the last column is a page turn, not a dead stop — the
    // behaviour the whole views-not-screens seam exists to keep identical.
    act(() => seen.onFocus(seen.perPage - 1))
    press('gp:dpad-right')
    expect(seen.page).toBe(1)
  })

  it('walks the tabs on L1/R1 and resets the cursor with them', async () => {
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()

    act(() => seen.onFocus(6))
    press('gp:r1')
    expect(seen.tab).toBe('games')
    expect(seen.focusIdx).toBe(0)
    press('gp:r1')
    expect(seen.tab).toBe('consoles')   // two tabs, so it wraps
    press('gp:l1')
    expect(seen.tab).toBe('games')
  })

  it('leaves on ○, and stands down while a modal is open', async () => {
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()

    act(() => useStore.setState({ modalDepth: 1 }))
    press('gp:dpad-right')
    expect(seen.focusIdx).toBe(0)
    press('gp:back')
    expect(useStore.getState().screen).toBe('store')

    act(() => useStore.setState({ modalDepth: 0 }))
    press('gp:back')
    expect(useStore.getState().screen).toBe('home')
  })

  it('lets a theme take the shortcuts it binds itself, and never ○', async () => {
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }}
                        omit={['nav', 'tabs']} />)
    await flush()

    press('gp:dpad-right')
    press('gp:r1')
    expect(seen.focusIdx).toBe(0)
    expect(seen.tab).toBe('consoles')

    // The way off the screen is not a theme's to drop.
    press('gp:back')
    expect(useStore.getState().screen).toBe('home')
  })
})

describe('the route in', () => {
  it('opens on △ from the dashboard and nowhere else', async () => {
    useStore.setState({ screen: 'home' })
    render(<DefaultShell homeView={() => null} libraryView={() => null} />)
    await flush()

    press('gp:y')
    expect(useStore.getState().screen).toBe('store')
    await flush()

    // Not from the library: △ is the search there, and two handlers on one
    // button is never what either of them meant.
    act(() => useStore.setState({ screen: 'library' }))
    press('gp:y')
    expect(useStore.getState().screen).toBe('library')
  })

  it('is also a button on the default bar', async () => {
    useStore.setState({ screen: 'home' })
    const r = render(<DefaultShell homeView={() => null} libraryView={() => null} />)
    await flush()
    const button = [...r.container.querySelectorAll('button')]
      .find(b => b.textContent?.includes('Store'))
    expect(button).toBeTruthy()
    fireEvent.click(button!)
    expect(useStore.getState().screen).toBe('store')
  })
})

describe('the Games tab', () => {
  it('says it is not here yet rather than drawing an empty library', async () => {
    const r = render(<StoreScreen />)
    await flush()
    press('gp:r1')
    expect(r.container.textContent).toContain('not here yet')
    // No fake rows, and nothing to press that would do nothing.
    expect(r.container.querySelectorAll('button')).toHaveLength(2)  // the two tabs
  })
})

describe('an install driven from the settings over this screen', () => {
  it('re-reads the catalogue and keeps the cursor on the pack it was on', async () => {
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()

    // The cursor is on System 03, fourth card of the first page.
    act(() => seen.onFocus(3))
    expect(seen.pageItems[seen.focusIdx].id).toBe('sys03')

    // System 00 is removed from somewhere else — every index shifts by one.
    vi.mocked(api.catalog.list).mockResolvedValue(CATALOGUE.filter(c => c.id !== 'sys00'))
    await emit('catalog:done', { action: 'remove', id: 'sys00', success: true })
    await flush()

    expect(seen.consoles).toHaveLength(13)
    expect(seen.pageItems[seen.focusIdx].id).toBe('sys03')   // still the same console
  })

  it('ignores an operation that failed', async () => {
    render(<StoreScreen view={() => null} />)
    await flush()
    vi.mocked(api.catalog.list).mockClear()
    await emit('catalog:done', { action: 'install', id: 'sys00', success: false })
    await flush()
    expect(api.catalog.list).not.toHaveBeenCalled()
  })
})
