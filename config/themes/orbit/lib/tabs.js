/** Three visible tabs. The host library is a child view of Consoles.
 * Keep the internal library state for the host screen and contextual hints. */
export const TABS = [
  ['home', 'Games'],
  ['systems', 'Consoles'],
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
    if (s.screen === 'library' && s.selectedSystemId && s.selectedSystemId !== '__all__') lastSystemId = s.selectedSystemId
    const next = s.screen === 'library' ? 'library'
      : (current === 'library' ? 'systems' : current)
    if (next !== current) {current = next; publish()}
  }

  const go = (tab, systems) => {
    if (sdk.nav.get().transition === 'launch') return
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
    const active = current === 'library' ? 'systems' : current
    const at = TABS.findIndex(([id]) => id === active)
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
          lastSystem: () => lastSystemId,
          rememberSystem: (id) => {if (id && id !== '__all__') lastSystemId = id}}
}
