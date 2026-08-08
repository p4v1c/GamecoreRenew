import { create } from 'zustand'

type Screen = 'home' | 'library'

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

  // Session
  sessionGameKey: string | null
  sessionSystemId: string | null

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
  sessionGameKey: null,
  sessionSystemId: null,
  remapRequest: 0,

  goHome: () => set({ screen: 'home', selectedSystemId: null, gridPage: 0, gridFocusIdx: 0 }),
  goLibrary: (id) => set({ screen: 'library', selectedSystemId: id, selectedGameIdx: 0 }),
  setGridFocus: (idx) => set({ gridFocusIdx: idx }),
  setGridPage: (page) => set({ gridPage: page }),
  setSelectedGameIdx: (idx) => set({ selectedGameIdx: idx }),
  setSession: (gameKey, systemId) => set({ sessionGameKey: gameKey, sessionSystemId: systemId }),
  openModal: () => set(s => ({ modalDepth: s.modalDepth + 1 })),
  closeModal: () => set(s => ({ modalDepth: Math.max(0, s.modalDepth - 1) })),
  setPowerPending: (action) => set({ powerPending: action }),
  requestRemap: () => set(s => ({ remapRequest: s.remapRequest + 1 })),
}))
