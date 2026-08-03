/**
 * Turning the box over, and changing how the shelf is stacked.
 *
 * Both are view state and nothing else — they move no selection, launch
 * nothing, and survive no reload. That is the line this theme is allowed to
 * cross: it may add ways of *looking*, never ways of *moving*. Scrolling,
 * sorting, searching, launching and ○ all stay exactly where the host put them,
 * which is why a shelf and the default list behave identically.
 *
 * The two triggers are L2 and R2 because they are the only face-adjacent
 * buttons the library leaves free: ↑↓ scroll, ✕ launches, ○ goes home, △ opens
 * search, □ opens the controller screen, and L1/R1 change the sort.
 *
 * ←→ are also free, and are wired to the *host's* own selection callback
 * rather than to anything of ours: on a shelf that runs left to right, pressing
 * right and having nothing happen reads as a broken screen. It is the same
 * clamped step ↑↓ already take, so nothing about the navigation differs — only
 * the number of buttons that reach it.
 */

export const MODES = ['shelf', 'stack', 'gallery']

const MODE_LABEL = { shelf: 'Shelf', stack: 'Stack', gallery: 'Gallery' }

export const createUseBrowse = (sdk) => {
  const { useState, useEffect, useRef } = sdk.ui

  return ({ selectedIdx, count, launching, onSelect }) => {
    const [mode, setMode] = useState('shelf')
    const [flipped, setFlipped] = useState(false)

    // Turning to the next box shows its front, always. Carrying a flip across
    // a selection means the shelf answers ← with a wall of back covers.
    useEffect(() => { setFlipped(false) }, [selectedIdx])

    // The bindings are registered once and read live state through refs: this
    // effect must not re-run on every step of a scroll, or a held direction
    // drops events while the listener is torn down and rebuilt.
    const live = useRef({ selectedIdx, count, launching, onSelect })
    live.current = { selectedIdx, count, launching, onSelect }

    const screen = sdk.nav.use((s) => s.screen)
    const modalDepth = sdk.nav.use((s) => s.modalDepth)
    const session = sdk.nav.use((s) => s.sessionGameKey)
    const gate = useRef(true)
    gate.current = screen === 'library' && modalDepth === 0 && session === null

    useEffect(() => {
      const blocked = () => !gate.current || live.current.launching

      const step = (delta) => {
        const { selectedIdx: i, count: n, onSelect: pick } = live.current
        if (blocked() || !n) return
        const next = Math.max(0, Math.min(n - 1, i + delta))
        if (next === i) return
        sdk.system.playSound('move')
        pick(next)
      }

      const offs = [
        sdk.input.onGp('gp:dpad-left', () => step(-1)),
        sdk.input.onGp('gp:dpad-right', () => step(1)),
        sdk.input.onGp('gp:l2', () => {
          if (blocked()) return
          sdk.system.playSound('confirm')
          setFlipped((f) => !f)
        }),
        sdk.input.onGp('gp:r2', () => {
          if (blocked()) return
          sdk.system.playSound('move')
          setMode((m) => MODES[(MODES.indexOf(m) + 1) % MODES.length])
        }),
      ]
      return () => offs.forEach((off) => off())
    }, [])

    return {
      mode,
      modeLabel: MODE_LABEL[mode],
      flipped,
      setMode,
      toggleFlip: () => setFlipped((f) => !f),
    }
  }
}
