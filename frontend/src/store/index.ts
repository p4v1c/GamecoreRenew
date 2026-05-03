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
}

export const useStore = create<GamecoreStore>((set) => ({
  screen: 'home',
  selectedSystemId: null,
  selectedGameIdx: 0,
  gridFocusIdx: 0,
  gridPage: 0,
  modalDepth: 0,
  sessionGameKey: null,
  sessionSystemId: null,

  goHome: () => set({ screen: 'home', selectedSystemId: null, gridPage: 0, gridFocusIdx: 0 }),
  goLibrary: (id) => set({ screen: 'library', selectedSystemId: id, selectedGameIdx: 0 }),
  setGridFocus: (idx) => set({ gridFocusIdx: idx }),
  setGridPage: (page) => set({ gridPage: page }),
  setSelectedGameIdx: (idx) => set({ selectedGameIdx: idx }),
  setSession: (gameKey, systemId) => set({ sessionGameKey: gameKey, sessionSystemId: systemId }),
  openModal: () => set(s => ({ modalDepth: s.modalDepth + 1 })),
  closeModal: () => set(s => ({ modalDepth: Math.max(0, s.modalDepth - 1) })),
}))
