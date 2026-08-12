/**
 * LibraryScreen — the library's behaviour.
 *
 * The markup lives in a view component, default or themed. This file is what
 * guarantees they behave identically: the sorting, the search, the launching
 * and the gamepad bindings are here, and a theme cannot replace them. The
 * search keyboard is here too, so a themed library cannot lose it.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useStore } from '../../store'
import { api, GameEntry, PlaytimeEntry, SystemEntry } from '../../api'
import { onGp } from '../../hooks/useGamepad'
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

interface Props {
  view?: React.ComponentType<LibraryViewProps>
}

export default function LibraryScreen({ view: View = DefaultLibraryView }: Props = {}) {
  const { selectedSystemId, selectedGameIdx, goHome, setSelectedGameIdx, setSession, modalDepth, screen, sessionGameKey } = useStore()
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
  const { openModal, closeModal } = useStore()
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

  const loadData = useCallback((systemId: string) => {
    setLoading(true)
    setLoadError(false)
    Promise.all([
      api.systems.get(systemId),
      api.games.list(systemId),
      api.playtime.forSystem(systemId),
    ]).then(([sys, gameList, rows]) => {
      setSystem(sys)
      setGames(gameList)
      const m: Record<string, PlaytimeEntry> = {}
      rows.forEach(r => { m[r.game_key] = r })
      setPlaytimeMap(m)
      setLoadError(false)
    }).catch(err => {
      console.error(err)
      setLoadError(true)
    }).finally(() => setLoading(false))
  }, [])

  // Reset launching state when session changes
  useEffect(() => {
    if (sessionGameKey === null) {
      setLaunching(false)
    }
  }, [sessionGameKey])

  useEffect(() => {
    setSystem(null)
    setGames([])
    setPlaytimeMap({})
    setSearch('')
    setLoading(false)
    setLoadError(false)
    setLaunching(false) // Reset launching when system changes

    if (!selectedSystemId) return
    loadData(selectedSystemId)
  }, [selectedSystemId, loadData])

  const sortedGames = [...games]
    .filter(g => formatGameName(g.display_name).toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      if (sort === 'name') return formatGameName(a.display_name).localeCompare(formatGameName(b.display_name))
      if (sort === 'playtime') return (playtimeMap[b.filename]?.total_secs || 0) - (playtimeMap[a.filename]?.total_secs || 0)
      if (sort === 'lastPlayed') {
        const da = playtimeMap[a.filename]?.last_played || ''
        const db = playtimeMap[b.filename]?.last_played || ''
        return db.localeCompare(da)
      }
      return 0
    })

  const selectedGame = sortedGames[selectedGameIdx] ?? sortedGames[0]

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
  }, [selectedGame?.filename, selectedSystemId])  // eslint-disable-line react-hooks/exhaustive-deps

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

  const cancelPendingLaunch = useCallback(() => {
    launchToken.current += 1
    setLaunching(false)
  }, [])

  const launchGame = useCallback(async () => {
    if (!selectedSystemId || !selectedGame || launching) return
    const token = ++launchToken.current
    setLaunching(true)
    playSound('launch')
    if (ceremonyMs > 0) {
      await new Promise(r => setTimeout(r, ceremonyMs))
      if (launchToken.current !== token) return   // ○ was pressed — never sent
    }
    try {
      await api.games.launch(selectedSystemId, selectedGame.path, selectedGame.filename)
      // Block inputs immediately — don't wait for the WebSocket game:started event
      setSession(selectedGame.filename, selectedSystemId)
    } catch (e) {
      console.error(e)
      setLaunching(false)
      setSession(null, null)
    }
  }, [selectedSystemId, selectedGame, launching, setSession, ceremonyMs])

  // Gamepad — guarded when modal is open or this screen is hidden behind home
  useEffect(() => {
    const blocked = () => {
      return screenRef.current !== 'library' ||
             modalDepthRef.current > 0 ||
             showSearchRef.current ||
             showOptionsRef.current ||
             launching ||
             sessionGameKey !== null
    }
    const offs = [
      onGp('gp:dpad-up',  () => { if (blocked() || !sortedGames.length) return; setSelectedGameIdx(Math.max(0, selectedGameIdx - 1)) }),
      onGp('gp:dpad-down',() => { if (blocked() || !sortedGames.length) return; setSelectedGameIdx(Math.min(sortedGames.length - 1, selectedGameIdx + 1)) }),
      onGp('gp:confirm',  () => { if (blocked()) return; launchGame() }),
      onGp('gp:back',     () => { if (screenRef.current !== 'library' || modalDepthRef.current > 0 || showOptionsRef.current) return; if (showSearchRef.current) { setShowSearch(false); return } cancelPendingLaunch(); goHome() }),
      onGp('gp:y',        () => { if (blocked()) return; setShowSearch(true) }),
      // R2, because every face button is already spoken for on this screen:
      // ✕ launches, ○ goes back, △ searches and □ is the controller screen.
      onGp('gp:r2',       () => { if (blocked() || !settledGame) return; setShowOptions(true) }),
      onGp('gp:l1', () => {
        if (blocked()) return
        setSort(s => { const i = SORT_KEYS.indexOf(s); return SORT_KEYS[(i - 1 + SORT_KEYS.length) % SORT_KEYS.length] })
      }),
      onGp('gp:r1', () => {
        if (blocked()) return
        setSort(s => { const i = SORT_KEYS.indexOf(s); return SORT_KEYS[(i + 1) % SORT_KEYS.length] })
      }),
    ]
    return () => offs.forEach(off => off())
  }, [selectedGameIdx, sortedGames.length, launchGame, goHome, setSelectedGameIdx, launching, sessionGameKey, cancelPendingLaunch])

  // When no system is selected, render nothing (screen is hidden by display:none anyway)
  if (!selectedSystemId) return null

  return (
    <>
      <View
        systemId={selectedSystemId}
        system={system}
        games={sortedGames}
        totalCount={games.length}
        playtime={playtimeMap}
        selectedIdx={selectedGameIdx}
        detailGame={settledGame}
        sort={sort}
        sortKeys={SORT_KEYS}
        sortLabels={SORT_LABELS}
        search={search}
        loading={loading}
        loadError={loadError}
        launching={launching}
        color={color}
        onSelect={setSelectedGameIdx}
        onSearch={(q) => { setSearch(q); setSelectedGameIdx(0) }}
        onSort={setSort}
        onLaunch={launchGame}
        onBack={goHome}
        onRetry={() => selectedSystemId && loadData(selectedSystemId)}
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
            systemId={selectedSystemId}
            rom={settledGame.filename}
            title={settledGame.display_name}
            onClose={() => setShowOptions(false)}
          />
        )}
      </AnimatePresence>
    </>
  )
}
