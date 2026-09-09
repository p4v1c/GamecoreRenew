/**
 * LibraryScreen — the library's behaviour.
 *
 * The markup lives in a view component, default or themed. This file is what
 * guarantees they behave identically: the sorting, the search, the launching
 * and the gamepad bindings are here, and a theme cannot replace them. The
 * search keyboard is here too, so a themed library cannot lose it.
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useStore } from '../../store'
import { api, GameEntry, PlaytimeEntry, SystemEntry } from '../../api'
import { onGp } from '../../hooks/useGamepad'
import { onWsEvent } from '../../hooks/useWebSocket'
import { hexToRgb, Overlay } from '../ui'
import { VirtualKeyboard } from '../ui/VirtualKeyboard'
import { systemColor } from '../../lib/format'
import { formatGameName } from '../../lib/formatGameName'
import { playSound } from '../../lib/sounds'
import { useThemeCtx } from '../ThemeSurface'
import DefaultLibraryView from './DefaultLibraryView'
import CoverImage from './CoverImage'
import GameMetaPanel from './GameMetaPanel'
import GameOptionsModal from '../modals/game/GameOptionsModal'
import { SORT_KEYS, SORT_LABELS, type SortKey, type LibraryViewProps } from './types'

const ALL_SYSTEMS = '__all__'
const playtimeKey = (game: GameEntry) => game.system_id ? `${game.system_id}:${game.filename}` : game.filename

interface Props {
  view?: React.ComponentType<LibraryViewProps>
  /** Shortcuts the theme binds itself; see ShellParts.libraryOmit. */
  omit?: string[]
}

export default function LibraryScreen({ view: View = DefaultLibraryView, omit }: Props = {}) {
  // One subscription per value. Bare, this screen re-rendered on every field
  // in the store — `gridFocusIdx` among them, so walking the dashboard
  // re-rendered the library hidden behind it. See shellRerender.test.tsx.
  const selectedSystemId = useStore(s => s.selectedSystemId)
  const selectedGameIdx = useStore(s => s.selectedGameIdx)
  const goHome = useStore(s => s.goHome)
  const setSelectedGameIdx = useStore(s => s.setSelectedGameIdx)
  const setSession = useStore(s => s.setSession)
  const modalDepth = useStore(s => s.modalDepth)
  const screen = useStore(s => s.screen)
  const sessionGameKey = useStore(s => s.sessionGameKey)
  const modalDepthRef = useRef(modalDepth)
  const screenRef = useRef(screen)
  useEffect(() => { modalDepthRef.current = modalDepth }, [modalDepth])
  useEffect(() => { screenRef.current = screen }, [screen])
  const [system, setSystem] = useState<SystemEntry | null>(null)
  const [games, setGames] = useState<GameEntry[]>([])
  const [playtimeMap, setPlaytimeMap] = useState<Record<string, PlaytimeEntry>>({})
  const [sort, setSort] = useState<SortKey>('name')
  const [search, setSearch] = useState('')
  const [launching, setLaunching] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [showOptions, setShowOptions] = useState(false)

  const showSearchRef = useRef(showSearch)
  useEffect(() => { showSearchRef.current = showSearch }, [showSearch])
  // The options panel registers its own dpad/✕/○ handlers. Without this the
  // library's handlers stay live underneath it, so moving the cursor in the
  // panel also moves it in the list — and ✕ launches the game.
  const showOptionsRef = useRef(showOptions)
  useEffect(() => { showOptionsRef.current = showOptions }, [showOptions])

  // The search keyboard counts as a modal: while it's open, global bindings
  // (Options → Settings, Share → Power) must not fire on top of it.
  const openModal = useStore(s => s.openModal)
  const closeModal = useStore(s => s.closeModal)
  useEffect(() => {
    if (!showSearch) return
    openModal()
    return () => closeModal()
  }, [showSearch]) // eslint-disable-line react-hooks/exhaustive-deps

  // Same for the options panel, and for the same reason: Options → Settings
  // and Share → Power are global, and would open a second surface on top.
  useEffect(() => {
    if (!showOptions) return
    openModal()
    return () => closeModal()
  }, [showOptions]) // eslint-disable-line react-hooks/exhaustive-deps

  // One resolver, shared with SystemCard and handed to themes as
  // sdk.format.systemColor — this used to be a third hand-rolled copy of the
  // same fallback chain.
  const color = systemColor({ id: selectedSystemId ?? '', color: system?.color })

  /**
   * Which load is allowed to write. Bumped by every call and by every change of
   * console, so a response can be matched against the request that is still
   * wanted.
   *
   * Three requests are in flight per load, none of them cancellable, and a
   * console with four hundred ROMs answers slower than an empty one. Opening
   * GameCube and stepping to PS2 before it answered used to render
   * `ps2:GameCube.rom`: the late reply overwrote the list, the cover requests
   * went out under the wrong console, and ✕ asked the backend to launch a pair
   * that does not exist. Clearing the state in the effect below does not help —
   * it runs before the reply, not after.
   *
   * A stale *failure* is the same bug wearing the other hat, and it was the
   * worse one: an old timeout replaced a library that had loaded perfectly well
   * with the retry screen.
   */
  const loadToken = useRef(0)
  // Written before a request starts. Unlike state, this already identifies the
  // wanted console during the render that precedes the clearing effect below.
  const requestedSystem = useRef<string | null>(null)

  const loadData = useCallback((systemId: string) => {
    requestedSystem.current = systemId
    const token = ++loadToken.current
    setLoading(true)
    setLoadError(false)
    const request: Promise<[SystemEntry, GameEntry[], PlaytimeEntry[]]> = systemId === ALL_SYSTEMS
      ? Promise.all([api.systems.list(), api.playtime.all()]).then(async ([systems, rows]) => {
          const lists = await Promise.all(systems.filter(s => s.kind === 'emulator' || s.type === 'emulator')
            .map(async system => (await api.games.list(system.id)).map(game => ({...game, system_id: system.id}))))
          return [{id: ALL_SYSTEMS, kind: 'emulator', label: 'All games'}, lists.flat(), rows]
        })
      : Promise.all([api.systems.get(systemId), api.games.list(systemId), api.playtime.forSystem(systemId)])
    request.then(([sys, gameList, rows]) => {
      if (loadToken.current !== token) return
      setSystem(sys)
      setGames(gameList)
      const m: Record<string, PlaytimeEntry> = {}
      rows.forEach(r => { m[systemId === ALL_SYSTEMS ? `${r.system_id}:${r.game_key}` : r.game_key] = r })
      setPlaytimeMap(m)
      setLoadError(false)
    }).catch(err => {
      if (loadToken.current !== token) return
      console.error(err)
      setLoadError(true)
    }).finally(() => {
      if (loadToken.current === token) setLoading(false)
    })
  }, [])

  /**
   * The one moment the hours on this screen can be out of date.
   *
   * The backend's playtime repair — which moves a game's hours onto the file
   * the library actually lists — no longer runs before the API answers: it
   * walks every ROM directory, so it made the size of the player's shelf into
   * the length of the boot. It runs beside the server now, and says so when it
   * has actually moved rows. Only then, and only the figures.
   */
  useEffect(() => {
    if (!selectedSystemId) return
    return onWsEvent('playtime:rekeyed', () => {
      const forSystem = selectedSystemId
      const request = forSystem === ALL_SYSTEMS ? api.playtime.all() : api.playtime.forSystem(forSystem)
      request.then(rows => {
        if (useStore.getState().selectedSystemId !== forSystem) return
        const m: Record<string, PlaytimeEntry> = {}
        rows.forEach(r => { m[forSystem === ALL_SYSTEMS ? `${r.system_id}:${r.game_key}` : r.game_key] = r })
        setPlaytimeMap(m)
      }).catch(() => {})
    })
  }, [selectedSystemId])

  // Reset launching state when session changes
  useEffect(() => {
    if (sessionGameKey === null) {
      launchLock.current = false
      setLaunching(false)
    }
  }, [sessionGameKey])

  useEffect(() => {
    // Retires whatever is still in flight for the console being left, including
    // the case this effect does not reload from: `selectedSystemId` back to null.
    loadToken.current += 1
    requestedSystem.current = null
    setSystem(null)
    setGames([])
    setPlaytimeMap({})
    setSearch('')
    setLoading(false)
    setLoadError(false)
    setLaunching(false) // Reset launching when system changes
    launchLock.current = false

    if (!selectedSystemId) return
    loadData(selectedSystemId)
  }, [selectedSystemId, loadData])

  /**
   * The display name of every game, formatted once per library.
   *
   * `formatGameName` strips regions, revisions and bracketed tags with a chain
   * of regexes. The list below called it twice per comparison, inside a sort,
   * on an array rebuilt by every render — and a render is what moving the
   * cursor causes. Measured on a thousand games, one step down the list cost
   * 2 998 calls to produce exactly the order that was already on screen.
   */
  const names = useMemo(() => {
    const m = new Map<GameEntry, { name: string; lower: string }>()
    for (const g of games) {
      const name = formatGameName(g.display_name)
      m.set(g, { name, lower: name.toLowerCase() })
    }
    return m
  }, [games])

  /**
   * Filtered and sorted, keyed on what actually decides the order.
   *
   * The cursor is deliberately not a dependency: a step must hand the view the
   * same array instance it had before. Shelf memoises its alphabet index on
   * that identity, and a fresh array per keypress threw the index away and
   * rebuilt it — on the navigation path, at the exact moment the box is
   * animating.
   */
  const sortedGames = useMemo(() => {
    const q = search.toLowerCase()
    const label = (g: GameEntry) => names.get(g)?.name ?? formatGameName(g.display_name)
    const out = q
      ? games.filter(g => (names.get(g)?.lower ?? label(g).toLowerCase()).includes(q))
      : games.slice()
    out.sort((a, b) => {
      if (sort === 'name') return label(a).localeCompare(label(b))
      if (sort === 'playtime') return (playtimeMap[playtimeKey(b)]?.total_secs || 0) - (playtimeMap[playtimeKey(a)]?.total_secs || 0)
      if (sort === 'lastPlayed') {
        const da = playtimeMap[playtimeKey(a)]?.last_played || ''
        const db = playtimeMap[playtimeKey(b)]?.last_played || ''
        return db.localeCompare(da)
      }
      return 0
    })
    return out
  }, [games, names, search, sort, playtimeMap])

  // A store change renders before the clearing effect above runs. Never pair
  // that new system id with the previous system's list during that one commit:
  // an <img> starts its request as soon as it is mounted, before effects can
  // remove it. Orbit exposed this as DS filenames requested under mgba and a
  // temporarily unresponsive grid while those wrong covers decoded.
  const dataReady = system?.id === selectedSystemId
  const displayedGames = dataReady ? sortedGames : []
  const effectiveError = requestedSystem.current === selectedSystemId && loadError
  const effectiveLoading = loading || (!dataReady && !effectiveError)

  const selectedGame = displayedGames[selectedGameIdx] ?? displayedGames[0]

  // Detail panel shows a debounced selection: updating it on every step of a
  // fast scroll thrashed AnimatePresence (the panel froze on the first game)
  // and fired a cover+metadata request per step. 150ms after the scroll
  // settles, the panel catches up in one clean transition.
  //
  // The system it belongs to is stored WITH it, and checked during render.
  // `systemId` comes from the store and changes the instant the player picks
  // another console, while this lags 150ms behind — so leaving a library
  // committed one frame pairing the new system with the previous system's
  // game, and the browser really did request
  // `/api/covers/rpcs3/Super Mario 64 DS.nds`. Clearing it from an effect is
  // too late: effects run after the DOM is committed, so the <img> has already
  // been created and the request already sent.
  const [settled, setSettled] = useState<{ game: GameEntry; systemId: string } | null>(null)
  useEffect(() => {
    if (!selectedGame || !selectedSystemId) { setSettled(null); return }
    const t = setTimeout(() => setSettled({ game: selectedGame, systemId: selectedSystemId }), 150)
    return () => clearTimeout(t)
  }, [selectedGame?.filename, selectedGame?.system_id, selectedSystemId])  // eslint-disable-line react-hooks/exhaustive-deps

  // What the view receives — unchanged in shape, so no theme has to care.
  const settledGame = settled?.systemId === selectedSystemId ? settled.game : null

  /**
   * The launch ceremony, and why the game waits for it.
   *
   * `setLaunching(true)` and the API call used to be consecutive lines, so the
   * emulator's window arrived over the top of the boot animation about a third
   * of the way in — the cartridge was still going into the slot when the game
   * took the screen. A theme cannot fix that from its side: it never calls the
   * launch, it only watches the flag.
   *
   * How long to wait is the theme's to say, because it is the theme's
   * animation. Themes that draw no ceremony — the default view among them —
   * declare nothing, get no delay, and behave exactly as before. The backend
   * bounds the value; this only has to trust the shape.
   *
   * The token is what makes ○ mean ○. Waiting opens a window in which the
   * player can leave the screen with a launch already promised, and without it
   * they would land on the dashboard and have the game start underneath them a
   * second later. Bumping the token is how leaving cancels a launch that has
   * not been sent yet — and it is a ref, not state, precisely so that cancelling
   * cannot race a render.
   */
  const ceremonyMs = useThemeCtx()?.manifest?.launch?.ms ?? 0
  const launchToken = useRef(0)
  /**
   * The launch gate, held synchronously.
   *
   * `launching` is state, so it turns true one render after ✕ — and the whole
   * point of the burst handling above is that presses arrive inside that
   * window. Two ✕ before the next render both read `launching === false` and
   * both sent a launch; on a theme with no ceremony the second one raced the
   * first all the way to the API, where the backend's lock refused it. A ref
   * is set before any `await`, so the second press has something to see.
   */
  const launchLock = useRef(false)

  const cancelPendingLaunch = useCallback(() => {
    launchToken.current += 1
    launchLock.current = false
    setLaunching(false)
    useStore.getState().setTransition(null)
  }, [])

  /**
   * Reads the pair to launch out of live state, not out of the render that
   * registered the handler.
   *
   * A step and a ✕ inside the same frame used to launch the *previous*
   * selection: the step wrote the cursor into the store synchronously, while
   * this closure still held the game from the last render. The cursor now comes
   * from the store and the list from a ref written during render, so the pair
   * is the one on screen at the moment of the press — and both halves come from
   * the same read, so no console/ROM mix is possible either.
   */
  const launchGame = useCallback(async () => {
    if (launchLock.current) return
    const selectedLibrary = useStore.getState().selectedSystemId
    const list = gamesRef.current
    const idx = useStore.getState().selectedGameIdx
    const game = list[idx] ?? list[0]
    const systemId = game?.system_id ?? selectedLibrary
    if (!systemId || !game) return
    launchLock.current = true
    const token = ++launchToken.current
    setLaunching(true)
    // Said in the store as well as in this screen's own state, because a theme
    // draws its ceremony from wherever it likes — the shell, a background
    // layer, an overlay of its own — and `launching` only reaches the library
    // view. See `transition` in the store.
    useStore.getState().setTransition('launch')
    playSound('launch')
    if (ceremonyMs > 0) {
      await new Promise(r => setTimeout(r, ceremonyMs))
      if (launchToken.current !== token) {
        useStore.getState().setTransition(null)
        return                                    // ○ was pressed — never sent
      }
    }
    try {
      await api.games.launch(systemId, game.path, game.filename)
      // A launch that was cancelled or superseded while the request was in
      // flight must not claim the session it no longer owns.
      if (launchToken.current !== token) return
      // Block inputs immediately — don't wait for the WebSocket game:started event
      setSession(game.filename, systemId)
      // The game owns the screen from here: the emulator overlay is above the
      // theme, so the ceremony has nothing left to cover.
      useStore.getState().setTransition(null)
    } catch (e) {
      console.error(e)
      // Same reasoning the other way round: a late failure belongs to its own
      // attempt, and must not clear a launch that has since succeeded.
      if (launchToken.current !== token) return
      launchLock.current = false
      setLaunching(false)
      useStore.getState().setTransition(null)
      setSession(null, null)
    }
  }, [setSession, ceremonyMs])

  // Everything the bindings below read at the moment a button is pressed,
  // rather than at the moment they were registered.
  //
  // The distinction is the whole of the fast-scroll bug. `onGp` handlers close
  // over the render that registered them, and a new closure only reaches the
  // window once React has rendered, committed, painted and flushed passive
  // effects. Presses arriving inside that window all computed their next index
  // from the same stale one and set it again — a no-op — so a burst of five
  // taps moved the cursor one row. It got worse the faster the player scrolled,
  // and worse again on a themed library over a few hundred games, because a
  // longer render is a wider window.
  //
  // Written during render, so they are current from the first press after a
  // change rather than one commit later. See libraryBurst.test.tsx.
  const countRef = useRef(0)
  const launchingRef = useRef(false)
  const launchRef = useRef(launchGame)
  const settledRef = useRef<GameEntry | null>(null)
  // The list as drawn, for the launch to index with the store's cursor.
  const gamesRef = useRef<GameEntry[]>(displayedGames)
  countRef.current = displayedGames.length
  launchingRef.current = launching
  launchRef.current = launchGame
  settledRef.current = settledGame
  gamesRef.current = displayedGames

  // `omit` is a prop and a fresh array on every parent render; the effect only
  // cares whether one id is in it.
  const omitOptions = !!omit?.includes('options')
  const omitNav = !!omit?.includes('nav')
  const omitConfirm = !!omit?.includes('confirm')
  const omitSort = !!omit?.includes('sort')

  // Gamepad — guarded when modal is open or this screen is hidden behind home
  useEffect(() => {
    const blocked = () => {
      return screenRef.current !== 'library' ||
             modalDepthRef.current > 0 ||
             showSearchRef.current ||
             showOptionsRef.current ||
             launchingRef.current ||
             useStore.getState().sessionGameKey !== null
    }
    // The cursor is read out of the store, not out of a closure: `set()` is
    // synchronous, so the second press of a burst steps from where the first
    // one left it even though nothing has re-rendered in between.
    const step = (delta: number) => {
      if (blocked()) return
      const n = countRef.current
      if (!n) return
      const from = useStore.getState().selectedGameIdx
      const next = Math.max(0, Math.min(n - 1, from + delta))
      if (next !== from) setSelectedGameIdx(next)
    }
    const offs = [
      onGp('gp:dpad-up',  () => { if (!omitNav) step(-1) }),
      onGp('gp:dpad-down',() => { if (!omitNav) step(1) }),
      onGp('gp:confirm',  () => { if (omitConfirm || blocked()) return; launchRef.current() }),
      onGp('gp:back',     () => { if (screenRef.current !== 'library' || modalDepthRef.current > 0 || showOptionsRef.current) return; if (showSearchRef.current) { setShowSearch(false); return } cancelPendingLaunch(); goHome() }),
      onGp('gp:y',        () => { if (blocked()) return; setShowSearch(true) }),
      // R2, because every face button is already spoken for on this screen:
      // ✕ launches, ○ goes back, △ searches and □ is the controller screen.
      //
      // Dropped entirely when the theme says it binds R2 itself — not merely
      // deferred, because both handlers would still fire. Shelf turns the box
      // with R2 and prints so in its own hint bar; leaving this here made one
      // press do two things, the second of which was never advertised.
      //
      // A theme that takes this shortcut leaves the per-game overlay picker
      // with no route on its screens. That is a real loss and it is stated
      // here rather than discovered: a wrong bezel is then only fixable from
      // the default UI or over SSH.
      ...(omitOptions ? [] : [
        onGp('gp:r2',     () => { if (blocked() || !settledRef.current) return; setShowOptions(true) }),
      ]),
      onGp('gp:l1', () => {
        if (omitSort || blocked()) return
        setSort(s => { const i = SORT_KEYS.indexOf(s); return SORT_KEYS[(i - 1 + SORT_KEYS.length) % SORT_KEYS.length] })
      }),
      onGp('gp:r1', () => {
        if (omitSort || blocked()) return
        setSort(s => { const i = SORT_KEYS.indexOf(s); return SORT_KEYS[(i + 1) % SORT_KEYS.length] })
      }),
    ]
    return () => offs.forEach(off => off())
    // Registered once, for the life of the screen. Every value the handlers
    // need is read live above — a dependency list that changed on each step
    // meant tearing eight listeners down and rebuilding them on every press,
    // which is both the stale-cursor bug and needless work per frame.
  }, [omitOptions, omitNav, omitConfirm, omitSort, goHome, setSelectedGameIdx, cancelPendingLaunch])

  // When no system is selected, render nothing (screen is hidden by display:none anyway)
  if (!selectedSystemId) return null

  return (
    <>
      <View
        systemId={selectedSystemId}
        system={system}
        games={displayedGames}
        totalCount={dataReady ? games.length : 0}
        playtime={playtimeMap}
        selectedIdx={selectedGameIdx}
        detailGame={settledGame}
        sort={sort}
        sortKeys={SORT_KEYS}
        sortLabels={SORT_LABELS}
        search={search}
        loading={effectiveLoading}
        loadError={effectiveError}
        launching={launching}
        color={color}
        onSelect={setSelectedGameIdx}
        onSearch={(q) => { setSearch(q); setSelectedGameIdx(0) }}
        onSort={key => { setSort(key); setSelectedGameIdx(0) }}
        onLaunch={launchGame}
        onBack={goHome}
        onRetry={() => selectedSystemId && loadData(selectedSystemId)}
        onOpenSearch={() => setShowSearch(true)}
        onOpenOptions={() => { if (settledGame) setShowOptions(true) }}
        Cover={CoverImage}
        Meta={GameMetaPanel}
      />

      {/* The host's, not the view's: a themed library cannot ship without a way
          to search, and the keyboard is what registers as a modal. */}
      <AnimatePresence>
        {showSearch && (
          <Overlay onClose={() => setShowSearch(false)}>
            <VirtualKeyboard
              // The hook a theme needs to dress this one.
              // Themes styled their settings keyboard and left this one in the
              // built-in grey, not by choice: the settings screens own their
              // wrapper and could scope `--gc-kb-*` to it, while this keyboard
              // is drawn by the host and no theme selector reached it.
              className="gc-search-kb"
              title="Search games"
              initialValue={search}
              placeholder="search a game…"
              onConfirm={val => { setSearch(val.trim()); setSelectedGameIdx(0); setShowSearch(false) }}
              onCancel={() => setShowSearch(false)}
            />
          </Overlay>
        )}
      </AnimatePresence>

      {/* Per-game options. Also the host's: which bezel a game gets is not a
          themable decision, and a theme that omitted it would leave the only
          remedy for a wrong overlay behind an SSH session. */}
      <AnimatePresence>
        {showOptions && settledGame && selectedSystemId && (
          <GameOptionsModal
            systemId={settledGame.system_id ?? selectedSystemId}
            rom={settledGame.filename}
            title={settledGame.display_name}
            onClose={() => setShowOptions(false)}
          />
        )}
      </AnimatePresence>
    </>
  )
}
