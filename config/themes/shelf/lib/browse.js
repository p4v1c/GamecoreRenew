/**
 * Turning the box over, and changing how the shelf is stacked.
 *
 * Both are view state and nothing else — they move no selection and launch
 * nothing. That is the line this theme is allowed to cross: it may add ways of
 * *looking*, never ways of *moving*. Scrolling, sorting, searching, launching
 * and ○ all stay exactly where the host put them, which is why a shelf and the
 * default list behave identically.
 *
 * **The layout is remembered, the flip is not**, and the asymmetry is the
 * point. A flip is about the box under the cursor and is cleared the moment
 * the cursor moves — remembering it would answer ← with a wall of back covers.
 * A layout is about how the player likes to read a library, and it used to be
 * forgotten on the way out of every console: three presses of R2 to get back
 * to Gallery, every single time, and again after a power cycle.
 *
 * ## Why `localStorage` and not the SDK
 *
 * `SDK_VERSION` exists to refuse a theme that calls a function the front end
 * does not have — `test_sdk_version_gate.py` records what it cost when it
 * failed. Adding `sdk.storage` for this would mean SDK 4 and `api: 4` here,
 * which makes Shelf incompatible with every older front end for the sake of
 * one string. `localStorage` is a browser API present in all of them, so this
 * adds no compatibility surface at all and the gate keeps meaning what it says.
 *
 * The key is namespaced to this theme. `gc:theme:*` belongs to the host —
 * `themeSafety.ts` keeps `gc:theme:crashes` and `gc:theme:safeMode` there —
 * and a theme writing into that space is a theme that can break safe mode.
 *
 * Every read and write is wrapped: a browser with storage disabled, a quota
 * exceeded, or a value someone edited by hand must cost the player a forgotten
 * preference, never a library that does not draw.
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

/** This theme's own corner of localStorage. NOT under `gc:theme:`, see above. */
export const MODE_KEY = 'gc:shelf:libraryMode'

/** The saved layout, or the default. Anything unrecognised is the default. */
export const readMode = () => {
  try {
    const saved = localStorage.getItem(MODE_KEY)
    return MODES.includes(saved) ? saved : MODES[0]
  } catch {
    return MODES[0]
  }
}

const writeMode = (mode) => {
  try {
    localStorage.setItem(MODE_KEY, mode)
  } catch {
    // Storage disabled or full. The layout still changes for this session;
    // only the memory of it is lost, which is the right thing to give up.
  }
}

export const createUseBrowse = (sdk) => {
  const { useState, useEffect, useRef } = sdk.ui

  return ({ selectedIdx, count, launching, onSelect }) => {
    // A lazy initialiser: read once per mount, not on every render. Leaving
    // the library and coming back mounts this hook again, and that is exactly
    // the moment the saved layout has to be picked up.
    const [mode, setMode] = useState(readMode)
    const [flipped, setFlipped] = useState(false)

    // The bindings below are registered once with `[]`, so they cannot read
    // `mode` from the closure — it would be for ever the value it had at mount,
    // and R2 would bounce between the first two layouts.
    //
    // Written by `applyMode` and NOT during render, which is the same lesson
    // the d-pad comment below records: a ref assigned while rendering is fresh
    // as of the last render, and that is not the same thing as fresh. R2 is
    // edge-triggered, so two quick presses are two events, and if the second
    // reads a ref React has not re-rendered yet, both step from the same
    // layout — measured, two presses moved it one place. Assigning at the
    // moment of the change makes the second press step from where the first
    // left it, exactly as reading the store does for the cursor.
    const modeRef = useRef(mode)

    // The one writer: nothing changes the layout without remembering it, and
    // nothing remembers it without the ref agreeing.
    const applyMode = (next) => {
      if (!MODES.includes(next)) return
      modeRef.current = next
      writeMode(next)
      setMode(next)
    }

    // Turning to the next box shows its front, always. Carrying a flip across
    // a selection means the shelf answers ← with a wall of back covers.
    useEffect(() => { setFlipped(false) }, [selectedIdx])

    // The bindings are registered once and read live state through refs: this
    // effect must not re-run on every step of a scroll, or a held direction
    // drops events while the listener is torn down and rebuilt.
    //
    // `selectedIdx` is deliberately NOT among them. A ref written during render
    // is fresh as of the last render, which is not the same thing as fresh: the
    // d-pad is edge-triggered, so five fast taps are five events, and any that
    // land before React has re-rendered would all step from the same index and
    // set it again. A burst of five moved the shelf one column. The cursor is
    // read from the store instead — `sdk.nav.get()` exists for exactly this,
    // and the store is written synchronously, so the second press of a burst
    // steps from where the first one left it.
    const live = useRef({ count, launching, onSelect })
    live.current = { count, launching, onSelect }

    const screen = sdk.nav.use((s) => s.screen)
    const modalDepth = sdk.nav.use((s) => s.modalDepth)
    const session = sdk.nav.use((s) => s.sessionGameKey)
    const gate = useRef(true)
    gate.current = screen === 'library' && modalDepth === 0 && session === null

    useEffect(() => {
      const blocked = () => !gate.current || live.current.launching

      const step = (delta) => {
        const { count: n, onSelect: pick } = live.current
        if (blocked() || !n) return
        const i = sdk.nav.get().selectedGameIdx
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
          const i = MODES.indexOf(modeRef.current)
          applyMode(MODES[(i + 1) % MODES.length])
        }),
      ]
      return () => offs.forEach((off) => off())
    }, [])

    return {
      mode,
      modeLabel: MODE_LABEL[mode],
      flipped,
      // The persisting writer, not the raw setter: a caller that reached for
      // `setMode` would change the layout for this session only, and the
      // forgetting would be invisible until the player came back.
      setMode: applyMode,
      toggleFlip: () => setFlipped((f) => !f),
    }
  }
}
