import { create } from 'zustand'

type Screen = 'home' | 'library'

/** One frozen session, as the backend describes it. */
export interface BackgroundSession {
  gameKey: string
  systemId: string
  session: number
  /** A tile with no ROM launches with `game_key === system_id`. */
  kind: 'game' | 'app'
}

interface GamecoreStore {
  // Navigation
  screen: Screen
  selectedSystemId: string | null
  selectedGameIdx: number
  gridFocusIdx: number
  gridPage: number

  // Modal focus lock — prevents background screens from consuming gamepad events
  modalDepth: number

  // Power action in flight ('shutdown' | 'restart') — freezes the UI so nothing
  // jumps back on screen while the OS is powering off
  powerPending: string | null

  /**
   * What the box is doing about power, as the backend last said.
   *
   * Here rather than inside the standby overlay because it is not the
   * overlay's business: the input bus has to know, and a theme may draw its
   * own screensaver — Summer does — or none at all. A guard that lived in the
   * picture would be lost with the picture.
   *
   *   'off'         awake
   *   'screensaver' the slideshow is up, the panel is still lit
   *   'sleep'       the backend has cut the panel through DPMS
   */
  standby: 'off' | 'screensaver' | 'sleep'
  setStandby: (stage: 'off' | 'screensaver' | 'sleep') => void

  /**
   * The session ON THE SCREEN — and it keeps that meaning exactly.
   *
   * Every reader of this asks the same question in different words: the pad
   * guard (`isPlaying`), the shell's decor, the library's bindings. All of
   * them mean "is a game in front of the player right now", and a suspended
   * one is not. So a session moving to the background writes `null` here, and
   * every one of those readers becomes correct without being touched — the
   * pad comes back on the dashboard while the game stays alive behind it.
   *
   * The alternative — keeping the key set and teaching each reader to also
   * check a state field — is the same fix written five times, with a sixth
   * reader added later that nobody remembers to teach.
   */
  sessionGameKey: string | null
  sessionSystemId: string | null

  /** Every suspended session, oldest first. Drawn by the session bar. */
  backgroundSessions: BackgroundSession[]
  setSessionState: (fg: { gameKey: string | null; systemId: string | null },
                    background: BackgroundSession[]) => void

  // Actions
  goHome: () => void
  goLibrary: (systemId: string) => void
  setGridFocus: (idx: number) => void
  setGridPage: (page: number) => void
  setSelectedGameIdx: (idx: number) => void
  setSession: (gameKey: string | null, systemId: string | null) => void
  openModal: () => void
  closeModal: () => void
  setPowerPending: (action: string | null) => void

  /**
   * Bumped when something asks for the mapping wizard — today, the toast shown
   * when a pad no SDL can name is plugged in.
   *
   * A counter and not a boolean: the shell reacts to the CHANGE, so asking
   * twice in a row works, and there is no flag left set for a later mount to
   * trip over. The toast cannot open the wizard itself — the shell owns which
   * modal is up, and the wizard has to displace whatever else is on screen.
   */
  remapRequest: number
  requestRemap: () => void
}

export const useStore = create<GamecoreStore>((set) => ({
  screen: 'home',
  selectedSystemId: null,
  selectedGameIdx: 0,
  gridFocusIdx: 0,
  gridPage: 0,
  modalDepth: 0,
  powerPending: null,
  standby: 'off',
  sessionGameKey: null,
  sessionSystemId: null,
  backgroundSessions: [],
  remapRequest: 0,

  goHome: () => set({ screen: 'home', selectedSystemId: null, gridPage: 0, gridFocusIdx: 0 }),
  goLibrary: (id) => set({ screen: 'library', selectedSystemId: id, selectedGameIdx: 0 }),
  setGridFocus: (idx) => set({ gridFocusIdx: idx }),
  setGridPage: (page) => set({ gridPage: page }),
  setSelectedGameIdx: (idx) => set({ selectedGameIdx: idx }),
  setSession: (gameKey, systemId) => set({ sessionGameKey: gameKey, sessionSystemId: systemId }),
  // Both halves in one write. Two `set` calls would render once with the game
  // gone from the screen and still absent from the session bar, which is one
  // frame of a box that has lost the player's game.
  setSessionState: (fg, background) => set({
    sessionGameKey: fg.gameKey, sessionSystemId: fg.systemId,
    backgroundSessions: background,
  }),
  openModal: () => set(s => ({ modalDepth: s.modalDepth + 1 })),
  closeModal: () => set(s => ({ modalDepth: Math.max(0, s.modalDepth - 1) })),
  setPowerPending: (action) => set({ powerPending: action }),
  setStandby: (stage) => set({ standby: stage }),
  requestRemap: () => set(s => ({ remapRequest: s.remapRequest + 1 })),
}))
