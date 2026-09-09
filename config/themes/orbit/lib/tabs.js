/** Orbit's four tabs, over a host that knows two screens.
 *
 * The mockup navigates between Games, Consoles, Library and Applications. The
 * host's store has `screen: 'home' | 'library'` and nothing else, so three of
 * the four live inside `home` as Orbit's own state and the fourth IS the host's
 * library screen.
 *
 * That mapping is not a workaround, it is the honest one: Library is the only
 * tab with behaviour behind it — sorting, the search keyboard, per-game
 * options, the launch itself — and all of that belongs to `LibraryScreen`. A
 * theme that drew its own would be reimplementing the one screen the contract
 * says not to (docs/themes/README.md §5, "Views, not screens"). The other three
 * are markup over data the host already hands to `homeView`.
 */
export const TABS = [
  ['home', 'Games'],
  ['systems', 'Consoles'],
  ['library', 'Library'],
  ['applications', 'Applications'],
]

export function createTabs(sdk) {
  const {useState, useEffect} = sdk.ui
  let current = 'home'
  //: The console the Library tab opens. Remembered so the tab is reachable
  //: before the player has picked one, and so returning to it lands where they
  //: left rather than on the first pack in the list.
  let lastSystemId = null
  const listeners = new Set()
  const publish = () => listeners.forEach((fn) => fn(current))

  /** The host owns which screen is up; Orbit's tab follows it, never the
   *  reverse. Leaving the library by ○ is a host binding, and the tab has to
   *  end up on something that is actually being drawn. */
  const reconcile = () => {
    const s = sdk.nav.get()
    if (s.selectedSystemId) lastSystemId = s.selectedSystemId
    const next = s.screen === 'library' ? 'library'
      : (current === 'library' ? 'home' : current)
    if (next !== current) {current = next; publish()}
  }

  const go = (tab, systems) => {
    if (tab === 'library') {
      const id = lastSystemId
        || systems?.find((s) => !s.kind || s.kind === 'emulator')?.id
        || systems?.[0]?.id
      // No console, no library: the host's screen renders nothing without one,
      // and a blank tab is worse than a tab that redirects.
      if (!id) {current = 'systems'; publish(); return}
      lastSystemId = id
      sdk.nav.goLibrary(id)
      current = 'library'
      publish()
      return
    }
    if (sdk.nav.get().screen === 'library') sdk.nav.goHome()
    current = tab
    publish()
  }

  const step = (delta, systems) => {
    const at = TABS.findIndex(([id]) => id === current)
    go(TABS[(at + delta + TABS.length) % TABS.length][0], systems)
  }

  function useTab() {
    const screen = sdk.nav.use((s) => s.screen)
    const [value, setValue] = useState(current)
    useEffect(() => {
      listeners.add(setValue)
      reconcile()
      setValue(current)
      return () => listeners.delete(setValue)
    }, [])
    useEffect(() => {reconcile(); setValue(current)}, [screen])
    return value
  }

  return {useTab, go, step, get: () => current,
          rememberSystem: (id) => {if (id) lastSystemId = id}}
}
