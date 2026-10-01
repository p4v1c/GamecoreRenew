/** Jelly's three tabs. A console's library is the host's screen, opened from
 * Consoles; while it is up, the Consoles tab stays lit. */
export const TABS = [
  ['play', 'Jouer'],
  ['collection', 'Collection'],
  ['consoles', 'Consoles'],
]

export function createTabs(sdk) {
  const {useState, useEffect} = sdk.ui
  let current = 'play'
  // Filters the Collection tab opens with, set by a shortcut on Play.
  let intent = null
  const listeners = new Set()
  const publish = () => listeners.forEach((fn) => fn(current))

  const go = (tab, opts = null) => {
    if (sdk.nav.use.getState?.().transition === 'launch') return
    if (sdk.nav.get().screen === 'library') sdk.nav.goHome()
    intent = opts
    if (tab !== current) { current = tab; sdk.system.playSound('move') }
    publish()
  }

  const step = (delta) => {
    const at = TABS.findIndex(([id]) => id === current)
    go(TABS[(at + delta + TABS.length) % TABS.length][0])
  }

  function useTab() {
    const [value, setValue] = useState(current)
    useEffect(() => {
      listeners.add(setValue)
      setValue(current)
      return () => listeners.delete(setValue)
    }, [])
    return value
  }

  /** Read once by the tab that was asked to open with it. */
  const takeIntent = () => { const i = intent; intent = null; return i }

  return {useTab, go, step, get: () => current, takeIntent}
}
