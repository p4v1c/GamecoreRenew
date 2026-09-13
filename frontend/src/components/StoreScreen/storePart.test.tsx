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
import {
  api,
  type CatalogEntry, type StoreJob, type StoreJobState,
  type StoreSearchAnswer, type StoreSearchResult,
} from '../../api'
import { CATALOG_FAILED } from '../../lib/catalog'
import { SEARCH_FAILED } from '../../lib/storeSearch'
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

/** Two results, which is enough to have a second one to walk to. */
const result = (id: string, title: string, extra: Partial<StoreSearchResult> = {}): StoreSearchResult => ({
  id, title, filename: `${title} (USA).zip`, format: 'zip', size: 4 * 1024 * 1024,
  systemId: 'sys00', provider: 'demo', source: `demo://sys00/${title}`,
  region: 'USA', languages: ['en'], ...extra,
})

const ANSWER: StoreSearchAnswer = {
  system: 'sys00', label: 'System 00', romsDir: 'emu/sys00',
  provider: 'demo', live: false, query: 'zelda',
  results: [result('r1', 'Zelda A'), result('r2', 'Zelda B', { format: 'nes' })],
}

/** One job, as the backend answers it. */
const job = (id: string, state: StoreJobState, extra: Partial<StoreJob> = {}): StoreJob => ({
  id, systemId: 'sys00', romsDir: 'emu/sys00', title: `Job ${id}`,
  filename: `Job ${id}.zip`, format: 'zip', size: 2048, provider: 'demo',
  state, reason: '', queuedAt: '2026-09-13T10:00:00+00:00', startedAt: '',
  endedAt: '', ...extra,
})

const flush = () => act(async () => { await new Promise(r => setTimeout(r, 0)) })

/**
 * Type into the host's on-screen keyboard and confirm.
 *
 * Through the keys rather than by calling the callback, because the keyboard
 * being the host's is part of what this file pins: a themed store cannot ship
 * without a way to type, and a test that bypassed it would still pass if the
 * keyboard stopped being rendered.
 */
const typeSearch = async (text: string) => {
  const key = (label: string) =>
    [...document.querySelectorAll('button')].find(b => b.textContent === label)
  if (!key('CLR')) throw new Error('the keyboard is not open')
  // Reopening it prefills the last query — see `initialValue` in the host.
  fireEvent.click(key('CLR')!)
  for (const ch of text) {
    const button = key(ch === ' ' ? 'SPACE' : ch)
    if (!button) throw new Error(`the keyboard has no key for "${ch}"`)
    fireEvent.click(button)
  }
  await act(async () => {
    fireEvent.click(key('↵ OK')!)
    await new Promise(r => setTimeout(r, 0))
  })
}
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
  vi.spyOn(api.catalog, 'busy').mockResolvedValue({ busy: false })
  // The three verbs return as soon as the CLI has started; `catalog:done` is
  // what closes a run, and this file fires that by hand.
  vi.spyOn(api.catalog, 'install').mockResolvedValue({} as never)
  vi.spyOn(api.catalog, 'remove').mockResolvedValue({} as never)
  vi.spyOn(api.catalog, 'reconfigure').mockResolvedValue({} as never)
  // The Games tab. `live: false` is the shipped answer — the only provider is
  // the demo one — and the tab has to say so rather than draw its rows the way
  // it will draw an indexer's.
  vi.spyOn(api.store, 'provider').mockResolvedValue({
    name: 'demo', label: 'Demo results', live: false, systemFirst: true })
  vi.spyOn(api.store, 'search').mockResolvedValue(ANSWER)
  // The queue. Empty by default and `downloadReady: false`, which is the
  // shipped answer for the whole of this step: a job is a real row that a
  // worker really runs, and nothing behind that worker can fetch a game.
  vi.spyOn(api.store, 'jobs').mockResolvedValue({ jobs: [], downloadReady: false })
  vi.spyOn(api.store, 'queue').mockImplementation(
    async (r: StoreSearchResult) => job(`job-${r.id}`, 'queued', { title: r.title }))
  vi.spyOn(api.store, 'cancel').mockImplementation(
    async (id: string) => job(id, 'cancelled'))
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
    // Searching is here; downloading is not, and they are two flags so a view
    // can draw results without promising a download.
    expect(seen.gamesReady).toBe(true)
    expect(seen.gamesDownloadReady).toBe(false)

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
  it('offers the installed consoles first, and only those', async () => {
    // Not a preference about menus. The ingestion class of a download is a
    // property of the pair (system, incoming format) and the directory it
    // lands in belongs to the system, so a result found without a console
    // attached could be neither placed nor classified — matrix §0, §1.3. And
    // a console that is not on the box would take the download into a
    // directory nothing scans, for a tile that is not on the grid.
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    press('gp:r1')

    expect(seen.gamesPhase).toBe('systems')
    expect(seen.gamesSystem).toBeNull()
    expect(seen.gamesSystems.map(s => s.id)).toEqual(['sys00', 'sys01', 'sys02'])
    expect(seen.gamesSystems.every(s => s.installed)).toBe(true)
  })

  it('says so rather than drawing a list when no console is installed', async () => {
    vi.mocked(api.catalog.list).mockResolvedValue(
      CATALOGUE.map(c => ({ ...c, installed: false })))
    const r = render(<StoreScreen />)
    await flush()
    press('gp:r1')
    expect(r.container.textContent).toContain('No console to search yet')
  })

  it('picks a console on ✕ and opens the keyboard with it', async () => {
    // One press rather than two: a console with nothing typed into it has
    // nothing to show, so a screen that stopped there would be a dead end.
    let seen!: StoreViewProps
    const r = render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    press('gp:r1')
    press('gp:confirm')
    await flush()

    expect(seen.gamesSystem?.id).toBe('sys00')
    expect(seen.gamesPhase).toBe('results')
    expect(r.container.textContent).toContain('Search System 00')
  })

  it('backs out of the keyboard all the way to the consoles', async () => {
    // Picking the wrong console is one press, and cancelling out of the
    // keyboard with nothing searched would otherwise leave the player looking
    // at an empty results list with no way to read it as anything but empty.
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    press('gp:r1')
    press('gp:confirm')
    await flush()
    expect(seen.gamesPhase).toBe('results')

    press('gp:back')
    await flush()
    expect(seen.gamesPhase).toBe('systems')
    expect(seen.gamesSystem).toBeNull()
    expect(useStore.getState().screen).toBe('store')
  })

  it('searches inside that console and never across the catalogue', async () => {
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    press('gp:r1')
    press('gp:confirm')
    await flush()
    await typeSearch('zelda')

    expect(api.store.search).toHaveBeenCalledWith('sys00', 'zelda')
    expect(seen.gamesQuery).toBe('zelda')
    expect(seen.gamesResults).toHaveLength(2)
    expect(seen.gamesRomsDir).toBe('emu/sys00')
    expect(seen.gamesAnswered).toBe(true)
  })

  it('pages the results as a column, not as the console grid', async () => {
    // A result is a filename, a size and a format — a line of text. Four side
    // by side on a television is four truncated names, so the shape travels in
    // `cols`/`rows` rather than being a second thing a theme has to know.
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    expect(seen.cols).toBe(4)

    press('gp:r1')
    expect(seen.cols).toBe(4)        // the console list is still a grid
    press('gp:confirm')
    await flush()
    await typeSearch('zelda')
    expect(seen.cols).toBe(1)
    expect(seen.perPage).toBe(seen.rows)
  })

  it('asks about a result, and says plainly that queueing is not downloading', async () => {
    // The sentence this replaced said nothing had been queued, because nothing
    // had. Something is queued now — and the panel has to be exactly as clear
    // about the difference, because this is the screen where a player learns
    // which of the two promises they are getting.
    const r = render(<StoreScreen />)
    await flush()
    press('gp:r1')
    press('gp:confirm')
    await flush()
    await typeSearch('zelda')

    press('gp:confirm')
    await flush()
    expect(r.container.textContent).toContain('It will not download')
    expect(r.container.textContent).toContain('Nothing is written into your ROM folder')
    // The one thing knowing the console first buys, shown: where it would go.
    expect(r.container.textContent).toContain('emu/sys00/')
  })

  it('holds the cursor still under the panel it opened', async () => {
    // It is a detail view. Without this, ✕ on it quietly swaps it for
    // whichever row the invisible cursor underneath had moved to.
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    press('gp:r1')
    press('gp:confirm')
    await flush()
    await typeSearch('zelda')

    press('gp:confirm')
    await flush()
    expect(seen.gamesAsked?.id).toBe('r1')
    press('gp:dpad-down')
    expect(seen.focusIdx).toBe(0)
    press('gp:confirm')
    expect(seen.gamesAsked?.id).toBe('r1')
  })

  it('says a format it was not told rather than inventing one', async () => {
    // A real indexer lists *releases*, and a release named "Zelda - Ocarina
    // of Time (USA)" names no format at all, so the backend sends an empty
    // one (services/store/search.py, SearchResult.format). The badge is drawn
    // like the region badge beside it — only when there is something in it —
    // and the panel says so in words, because a plausible extension invented
    // on this screen is the one thing the ingestion steps key on.
    vi.mocked(api.store.search).mockResolvedValue({
      ...ANSWER, results: [result('r1', 'Zelda A', { format: '' })],
    })
    const r = render(<StoreScreen />)
    await flush()
    press('gp:r1')
    press('gp:confirm')
    await flush()
    await typeSearch('zelda')

    press('gp:confirm')
    await flush()
    expect(r.container.textContent).toContain('not stated by the source')
  })

  it('says out loud that invented results are invented', async () => {
    // The demo provider makes up rows that look exactly like an indexer's. A
    // tab that drew them identically would invite a player to press ✕ on a
    // game that does not exist — a worse lie than the empty state it replaced.
    const r = render(<StoreScreen />)
    await flush()
    press('gp:r1')
    press('gp:confirm')
    await flush()
    await typeSearch('zelda')
    expect(r.container.textContent).toContain('These results are made up')
  })

  it('steps back through its phases before it leaves the screen', async () => {
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    press('gp:r1')
    press('gp:confirm')
    await flush()
    await typeSearch('zelda')
    press('gp:confirm')                       // ask about the first result
    await flush()
    expect(seen.gamesAsked).not.toBeNull()

    press('gp:back')
    expect(seen.gamesAsked).toBeNull()        // back to the results
    expect(seen.gamesPhase).toBe('results')
    press('gp:back')
    expect(seen.gamesPhase).toBe('systems')   // back to the consoles
    expect(useStore.getState().screen).toBe('store')
    press('gp:back')
    expect(useStore.getState().screen).toBe('home')   // and only then, home
  })

  it('tells a failed search apart from a query that matched nothing', async () => {
    // Blaming the query for a provider that did not answer sends the player
    // off to retype a title that was fine.
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    press('gp:r1')
    press('gp:confirm')
    await flush()

    vi.mocked(api.store.search).mockRejectedValueOnce(new Error('502'))
    await typeSearch('zelda')
    expect(seen.gamesError).toBe(SEARCH_FAILED)
    expect(seen.gamesAnswered).toBe(false)

    // △ reopens the keyboard: the failed search closed it, and the error
    // message says so rather than leaving the player on a dead screen.
    press('gp:y')
    vi.mocked(api.store.search).mockResolvedValueOnce({ ...ANSWER, results: [] })
    await typeSearch('nothing at all')
    expect(seen.gamesError).toBe('')
    expect(seen.gamesAnswered).toBe(true)
    expect(seen.gamesResults).toEqual([])
  })

  it('draws those two states as two different sentences', async () => {
    const r = render(<StoreScreen />)
    await flush()
    press('gp:r1')
    press('gp:confirm')
    await flush()

    vi.mocked(api.store.search).mockResolvedValueOnce({ ...ANSWER, results: [] })
    await typeSearch('zelda')
    expect(r.container.textContent).toContain('Nothing matched')

    press('gp:y')
    vi.mocked(api.store.search).mockRejectedValueOnce(new Error('502'))
    await typeSearch('zelda')
    expect(r.container.textContent).toContain(SEARCH_FAILED)
    expect(r.container.textContent).not.toContain('Nothing matched')
  })

  it('lets a theme list results without owning the search', async () => {
    // The same seam as the Consoles tab's: a view draws the rows, and the
    // callbacks are its only reach into what pressing one means. A theme that
    // ran its own search would be the second implementation of it.
    let seen!: StoreViewProps
    const Themed = (p: StoreViewProps) => {
      seen = p
      return <div data-testid="themed">{p.gamesResultsPage.map(x => x.title).join(',')}</div>
    }
    const r = render(<StoreScreen view={Themed} />)
    await flush()
    press('gp:r1')

    // Driven through the props, the way a theme with its own buttons would.
    act(() => seen.onGamesSystem(seen.gamesSystems[1]))
    await flush()
    expect(seen.gamesSystem?.id).toBe('sys01')
    await typeSearch('zelda')

    expect(api.store.search).toHaveBeenCalledWith('sys01', 'zelda')
    expect(r.getByTestId('themed').textContent).toBe('Zelda A,Zelda B')

    act(() => seen.onGamesAsk(seen.gamesResults[1]))
    expect(seen.gamesAsked?.id).toBe('r2')
    act(() => seen.onGamesBack())
    expect(seen.gamesAsked).toBeNull()
  })
})

describe('a run that finishes while this screen is up', () => {
  it('re-reads the catalogue and keeps the cursor on the pack it was on', async () => {
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()

    // The cursor is on System 03, fourth card of the first page.
    act(() => seen.onFocus(3))
    expect(seen.pageItems[seen.focusIdx].id).toBe('sys03')

    // System 00 is removed — every index shifts by one. From this screen now,
    // or from the applications page over it; the screen cannot tell and does
    // not need to.
    vi.mocked(api.catalog.list).mockResolvedValue(CATALOGUE.filter(c => c.id !== 'sys00'))
    await emit('catalog:done', { action: 'remove', id: 'sys00', success: true })
    await flush()

    expect(seen.consoles).toHaveLength(13)
    expect(seen.pageItems[seen.focusIdx].id).toBe('sys03')   // still the same console
  })

  it('re-reads after a failure too, and still does not move the cursor', async () => {
    // It used to return early on `success: false` and re-read nothing. That is
    // wrong for the failure that actually happens: `_run_cli` kills the CLI at
    // `_CLI_TIMEOUT` and reports `success: false` after however much of the
    // work it had already done, and `installed` is read from the systems.json
    // that work writes. Skipping the re-read leaves the grid saying "not
    // installed" about a pack that is now half on the box.
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()

    act(() => seen.onFocus(3))
    vi.mocked(api.catalog.list).mockClear()
    await emit('catalog:done', { action: 'install', id: 'sys09', success: false })
    await flush()

    expect(api.catalog.list).toHaveBeenCalled()
    expect(seen.pageItems[seen.focusIdx].id).toBe('sys03')
    expect(seen.actionError).toBe(CATALOG_FAILED)
    expect(seen.busy).toBe(false)          // and the grid is released
  })
})

describe('installing a console, which is what this screen is for', () => {
  it('installs on ✕ and holds the whole grid until it finishes', async () => {
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()

    // System 03 is not installed — only the first three are.
    act(() => seen.onFocus(3))
    press('gp:confirm')
    await flush()
    expect(api.catalog.install).toHaveBeenCalledWith('sys03')
    expect(seen.workingId).toBe('sys03')

    // One action at a time, box-wide: the backend answers 409 to a second, so
    // the cards are held rather than offering three presses that would fail.
    expect(seen.busy).toBe(true)
    act(() => seen.onFocus(4))
    press('gp:confirm')
    await flush()
    expect(api.catalog.install).toHaveBeenCalledTimes(1)

    await emit('catalog:done', { action: 'install', id: 'sys03', success: true })
    expect(seen.workingId).toBe('')
    expect(seen.busy).toBe(false)
  })

  it('asks twice before removing, and any direction is the answer no', async () => {
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()

    // System 00 is installed. ✕ arms, it does not remove.
    act(() => seen.onFocus(0))
    press('gp:confirm')
    await flush()
    expect(seen.armedId).toBe('sys00')
    expect(api.catalog.remove).not.toHaveBeenCalled()

    // Stepping away disarms — ✕ lands wherever the cursor happens to be, and
    // that is the whole reason the second press is safe to offer.
    press('gp:dpad-right')
    expect(seen.armedId).toBe('')
    press('gp:dpad-left')
    press('gp:confirm')
    await flush()
    expect(seen.armedId).toBe('sys00')
    press('gp:confirm')
    await flush()
    expect(api.catalog.remove).toHaveBeenCalledWith('sys00')
  })

  it('reconfigures on △, and only something that is installed', async () => {
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()

    act(() => seen.onFocus(3))          // not installed
    press('gp:y')
    await flush()
    expect(api.catalog.reconfigure).not.toHaveBeenCalled()

    act(() => seen.onFocus(0))          // installed
    press('gp:y')
    await flush()
    expect(api.catalog.reconfigure).toHaveBeenCalledWith('sys00')
  })

  it('shows the run\u2019s output, so a slow Flatpak is not a frozen card', async () => {
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    await emit('catalog:log', { line: 'Installing org.DolphinEmu.dolphin-emu…' })
    expect(seen.log).toEqual(['Installing org.DolphinEmu.dolphin-emu\u2026'])
  })

  it('holds the grid for a run another screen started', async () => {
    // The settings modal opens over this screen and leaves it mounted. There
    // is no `catalog:start` event, so output arriving with nothing of ours
    // running is what says somebody else took the lock.
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    expect(seen.busy).toBe(false)
    await emit('catalog:log', { line: 'Installing steam…' })
    expect(seen.busy).toBe(true)
    expect(seen.workingId).toBe('')      // not ours, so no card claims it
  })

  it('lets a theme take the two action buttons and keeps the actions', async () => {
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }}
                        omit={['actions']} />)
    await flush()

    act(() => seen.onFocus(3))
    press('gp:confirm')
    press('gp:y')
    await flush()
    expect(api.catalog.install).not.toHaveBeenCalled()
    expect(api.catalog.reconfigure).not.toHaveBeenCalled()

    // The buttons are the theme's; what they mean is not. `onAct` still
    // installs, and still through the host's one-at-a-time rule.
    act(() => seen.onAct(seen.pageItems[3]))
    await flush()
    expect(api.catalog.install).toHaveBeenCalledWith('sys03')
  })
})

describe('the default view now that the cards do something', () => {
  it('draws the action the focused card offers, and no stale signpost', async () => {
    const r = render(<StoreScreen />)
    await flush()
    expect(r.container.textContent).toContain('NOT INSTALLED')
    // The line that said installing lived in the settings. It does not.
    expect(r.container.textContent).not.toContain('Settings')
    // The cursor opens on System 00, which is installed — so the hint is the
    // pair of things an installed card offers, not "install".
    expect(r.container.textContent).toContain('✕ remove · △ reconfigure')
  })

  it('says a card is armed rather than letting the first press look like nothing', async () => {
    const r = render(<StoreScreen />)
    await flush()
    press('gp:confirm')                  // System 00, installed
    await flush()
    expect(r.container.textContent).toContain('✕ AGAIN')
  })
})

describe('the queue, which is what asking for a game now means', () => {
  /** Walk to the Games tab, pick a console, search, and open one result. */
  const toAskedPanel = async (seenOf?: () => StoreViewProps) => {
    press('gp:r1')
    press('gp:confirm')
    await flush()
    await typeSearch('zelda')
    press('gp:confirm')
    await flush()
    return seenOf
  }

  it('hands a view the queue, its shape and its two actions', async () => {
    // The contract, in one place: a theme must be able to draw a queue without
    // owning what a state means, which row can still be stopped, or what
    // happens when one is.
    let seen!: StoreViewProps
    vi.mocked(api.store.jobs).mockResolvedValue({
      jobs: [job('a', 'running'), job('b', 'queued'), job('c', 'failed')],
      downloadReady: false,
    })
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()

    expect(seen.gamesJobs.map(j => j.id)).toEqual(['a', 'b', 'c'])
    expect(seen.gamesJobsLive).toBe(2)
    expect(seen.gamesJobsError).toBe('')
    expect(seen.gamesQueueError).toBe('')
    expect(seen.gamesQueueing).toBe(false)
    // Still false, and still the flag that promises bytes in a ROM directory.
    // A queue existing is not the same promise as a download working.
    expect(seen.gamesDownloadReady).toBe(false)
    expect(typeof seen.onGamesQueue).toBe('function')
    expect(typeof seen.onGamesCancelJob).toBe('function')
    expect(typeof seen.onGamesQueueOpen).toBe('function')
  })

  it('✕ on the asked panel queues it and shows the player the row', async () => {
    // The press wrote something down. A screen that stayed on the panel would
    // have given no evidence of it — which is exactly how the version of this
    // button that recorded a choice nothing acted on read as a button that
    // does nothing.
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    await toAskedPanel()
    expect(seen.gamesAsked?.id).toBe('r1')

    vi.mocked(api.store.jobs).mockResolvedValue({
      jobs: [job('job-r1', 'queued', { title: 'Zelda A' })],
      downloadReady: false,
    })
    press('gp:confirm')
    await flush()

    expect(api.store.queue).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'r1', source: 'demo://sys00/Zelda A' }))
    expect(seen.gamesPhase).toBe('queue')
    expect(seen.gamesAsked).toBeNull()
    expect(seen.gamesJobs.map(j => j.id)).toEqual(['job-r1'])
  })

  it('△ opens the queue from the console list, and ○ closes it again', async () => {
    // The only free button left on this tab: ✕ picks and asks, ○ leaves, L1/R1
    // walk the tabs, and □ is the shell's controller screen.
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    press('gp:r1')
    expect(seen.gamesPhase).toBe('systems')

    press('gp:y')
    await flush()
    expect(seen.gamesPhase).toBe('queue')

    press('gp:back')
    await flush()
    expect(seen.gamesPhase).toBe('systems')
  })

  it('closes the queue onto whatever was underneath it', async () => {
    // Its own flag and not a state of the search, which is what lets a player
    // check the queue mid-search and come back to their results.
    let seen!: StoreViewProps
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    await toAskedPanel()
    press('gp:confirm')                     // queue it → the queue opens
    await flush()
    expect(seen.gamesPhase).toBe('queue')

    press('gp:back')
    await flush()
    // Back onto the results, with the search still answered underneath.
    expect(seen.gamesPhase).toBe('results')
    expect(seen.gamesResults).toHaveLength(2)
  })

  it('walks the queue as a column and cancels the row under the cursor', async () => {
    let seen!: StoreViewProps
    vi.mocked(api.store.jobs).mockResolvedValue({
      jobs: [job('a', 'running'), job('b', 'queued')],
      downloadReady: false,
    })
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    press('gp:r1')
    press('gp:y')
    await flush()

    expect(seen.cols).toBe(1)
    expect(seen.gamesJobsPage.map(j => j.id)).toEqual(['a', 'b'])
    press('gp:dpad-down')
    expect(seen.focusIdx).toBe(1)

    press('gp:confirm')
    await flush()
    expect(api.store.cancel).toHaveBeenCalledWith('b')
  })

  it('absorbs ✕ on a job nothing can stop any more', async () => {
    // A finished row takes the press silently rather than turning it into an
    // error the player did not cause.
    let seen!: StoreViewProps
    vi.mocked(api.store.jobs).mockResolvedValue({
      jobs: [job('a', 'failed', { reason: 'no acquisition provider is configured on this box' })],
      downloadReady: false,
    })
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    press('gp:r1')
    press('gp:y')
    await flush()

    press('gp:confirm')
    await flush()
    expect(api.store.cancel).not.toHaveBeenCalled()
    expect(seen.gamesQueueError).toBe('')
  })

  it('draws the queue, its states and the reason a job failed', async () => {
    vi.mocked(api.store.jobs).mockResolvedValue({
      jobs: [job('a', 'failed', {
        title: 'Zelda A',
        reason: 'no acquisition provider is configured on this box',
      })],
      downloadReady: false,
    })
    const r = render(<StoreScreen />)
    await flush()
    press('gp:r1')
    press('gp:y')
    await flush()

    expect(r.container.textContent).toContain('Zelda A')
    expect(r.container.textContent).toContain('FAILED')
    // The reason is the half a player can act on: "no provider" and "the box
    // stopped" are two different failures, and a row that only said FAILED
    // would make them one.
    expect(r.container.textContent).toContain('no acquisition provider is configured')
    // And the queue says out loud that it is not a download. Same rule as the
    // banner over invented results: the screen must not look like something
    // it is not, and this one persists across a reboot.
    expect(r.container.textContent).toContain('Nothing here downloads yet')
  })

  it('says nothing was asked for rather than drawing an empty list as an error', async () => {
    const r = render(<StoreScreen />)
    await flush()
    press('gp:r1')
    press('gp:y')
    await flush()
    expect(r.container.textContent).toContain('Nothing asked for yet')
  })

  it('tells a queue that could not be read from a queue with nothing in it', async () => {
    vi.mocked(api.store.jobs).mockRejectedValue(new Error('down'))
    const r = render(<StoreScreen />)
    await flush()
    press('gp:r1')
    press('gp:y')
    await flush()
    expect(r.container.textContent).toContain('The queue could not be read')
    expect(r.container.textContent).not.toContain('Nothing asked for yet')
  })

  it('shows why the box refused, in the box’s own words', async () => {
    let seen!: StoreViewProps
    vi.mocked(api.store.queue).mockRejectedValue(
      new Error('that is already in the queue'))
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    await toAskedPanel()
    press('gp:confirm')
    await flush()

    expect(seen.gamesQueueError).toBe('that is already in the queue')
    // The panel is put down either way, and the queue is NOT opened: there is
    // no new row to show, and the refusal is on screen where the player is.
    expect(seen.gamesPhase).toBe('results')
  })

  it('hears about a job moving without being asked', async () => {
    // The worker finishes jobs on its own, and the screen that queued one is
    // usually still open when it does.
    let seen!: StoreViewProps
    vi.mocked(api.store.jobs).mockResolvedValue({
      jobs: [job('a', 'running')], downloadReady: false })
    render(<StoreScreen view={(p: StoreViewProps) => { seen = p; return null }} />)
    await flush()
    expect(seen.gamesJobs[0].state).toBe('running')

    vi.mocked(api.store.jobs).mockResolvedValue({
      jobs: [job('a', 'failed', { reason: 'no acquisition provider is configured on this box' })],
      downloadReady: false,
    })
    await emit('store:jobs', { job: job('a', 'failed') })
    expect(seen.gamesJobs[0].state).toBe('failed')
    expect(seen.gamesJobsLive).toBe(0)
  })
})
