/**
 * The store every screen and every theme reads.
 *
 * Three of its fields are not preferences, they are locks: `modalDepth` decides
 * whether the background screen still consumes gamepad events, `sessionGameKey`
 * decides whether the whole UI is deaf while a game runs, and `powerPending`
 * freezes the interface while the OS goes down. Getting any of them wrong does
 * not look like a bug — it looks like a controller that stopped working.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { useStore } from './index'

const initial = useStore.getState()

beforeEach(() => {
  useStore.setState({
    screen: 'home',
    selectedSystemId: null,
    selectedGameIdx: 0,
    gridFocusIdx: 0,
    gridPage: 0,
    modalDepth: 0,
    powerPending: null,
    sessionGameKey: null,
    sessionSystemId: null,
  })
})

describe('screen transitions', () => {
  it('opens a library on the system that was picked', () => {
    useStore.getState().goLibrary('some-system')
    const s = useStore.getState()
    expect(s.screen).toBe('library')
    expect(s.selectedSystemId).toBe('some-system')
  })

  it('starts a freshly opened library at its first game', () => {
    useStore.setState({ selectedGameIdx: 12 })
    useStore.getState().goLibrary('another-system')
    expect(useStore.getState().selectedGameIdx).toBe(0)
  })

  it('forgets the grid position when going home', () => {
    // Going home from page 3 used to come back to page 3 of a grid that may
    // no longer have one — the tile count changes when a pack is installed
    // or removed from the very screen this returns to.
    useStore.setState({ screen: 'library', gridPage: 3, gridFocusIdx: 7,
                        selectedSystemId: 'some-system' })
    useStore.getState().goHome()
    const s = useStore.getState()
    expect(s).toMatchObject({ screen: 'home', selectedSystemId: null,
                              gridPage: 0, gridFocusIdx: 0 })
  })

  it('keeps the running session across a trip home', () => {
    // The home screen is reachable while a game runs, and the session is what
    // tells the UI to stay deaf. Clearing it here would hand the pad back to
    // the interface with an emulator still in the foreground.
    useStore.getState().setSession('some-game', 'some-system')
    useStore.getState().goHome()
    expect(useStore.getState().sessionGameKey).toBe('some-game')
  })
})

describe('modal depth', () => {
  it('counts nested modals rather than holding a boolean', () => {
    const { openModal, closeModal } = useStore.getState()
    openModal()
    openModal()
    expect(useStore.getState().modalDepth).toBe(2)
    closeModal()
    // Still locked: a boolean would have unlocked the background here, which
    // is the whole reason this is a depth.
    expect(useStore.getState().modalDepth).toBe(1)
    closeModal()
    expect(useStore.getState().modalDepth).toBe(0)
  })

  it('never goes negative', () => {
    // An unbalanced close — a modal unmounted by a screen change while its own
    // cleanup also runs — would otherwise leave the depth at -1, and every
    // later open would test as "no modal" while one is on screen.
    const { closeModal, openModal } = useStore.getState()
    closeModal()
    closeModal()
    expect(useStore.getState().modalDepth).toBe(0)
    openModal()
    expect(useStore.getState().modalDepth).toBe(1)
  })
})

describe('session and power', () => {
  it('clears both halves of a session together', () => {
    const { setSession } = useStore.getState()
    setSession('some-game', 'some-system')
    setSession(null, null)
    const s = useStore.getState()
    expect(s.sessionGameKey).toBeNull()
    expect(s.sessionSystemId).toBeNull()
  })

  it('holds the power action that is in flight', () => {
    useStore.getState().setPowerPending('shutdown')
    expect(useStore.getState().powerPending).toBe('shutdown')
    useStore.getState().setPowerPending(null)
    expect(useStore.getState().powerPending).toBeNull()
  })
})

describe('grid selection', () => {
  it('moves focus and page independently', () => {
    // They are separate on purpose: paging keeps the cursor where it was on
    // the new page, rather than snapping it back to the first tile.
    useStore.getState().setGridFocus(4)
    useStore.getState().setGridPage(2)
    const s = useStore.getState()
    expect(s.gridFocusIdx).toBe(4)
    expect(s.gridPage).toBe(2)
  })
})

describe('the initial state', () => {
  it('boots on the home screen with nothing selected and nothing locked', () => {
    // What a cold start must look like. A box that boots with modalDepth at 1
    // ignores the controller entirely, with no visible modal to close.
    expect(initial.screen).toBe('home')
    expect(initial.selectedSystemId).toBeNull()
    expect(initial.modalDepth).toBe(0)
    expect(initial.sessionGameKey).toBeNull()
    expect(initial.powerPending).toBeNull()
  })
})
