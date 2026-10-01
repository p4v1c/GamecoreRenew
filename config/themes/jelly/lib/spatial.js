/** Pad navigation over the controls actually on screen.
 *
 * Every Jelly screen is a set of `[data-nav]` buttons; the d-pad moves DOM
 * focus between them by position, ✕ clicks the focused one. One hook for all
 * of them, so a grid, a hero card and a keyboard move the same way.
 *
 * The host's input bus already handles repeat, the stick and dead zones; this
 * only decides where a step lands. Each screen says when it owns the pad
 * (`allowed`), and stands down otherwise, so two layers never answer one press.
 */
const DIRS = {left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1]}

// A document with no layout engine (a test's jsdom) reports no boxes at all;
// there, everything not disabled counts as shown.
const laidOut = () => document.documentElement.getClientRects().length > 0
const visible = (el) => !el.disabled && el.getAttribute('aria-disabled') !== 'true'
  && (el.getClientRects().length > 0 || !laidOut())

/** The next control in a direction. Controls in line with the current one
 * (sharing a row or a column) win over closer ones off to the side, so a step
 * never jumps diagonally when a straight answer exists. */
export function nextInDirection(from, items, [dx, dy]) {
  const a = from.getBoundingClientRect()
  const ax = (a.left + a.right) / 2
  const ay = (a.top + a.bottom) / 2
  let inline = null
  let loose = null
  for (const el of items) {
    if (el === from) continue
    const b = el.getBoundingClientRect()
    const bx = (b.left + b.right) / 2
    const by = (b.top + b.bottom) / 2
    const forward = dx * (bx - ax) + dy * (by - ay)
    if (forward <= 2) continue
    const side = Math.abs(dy * (bx - ax) + dx * (by - ay))
    const overlaps = dx
      ? b.top < a.bottom - 2 && b.bottom > a.top + 2
      : b.left < a.right - 2 && b.right > a.left + 2
    if (overlaps) {
      const score = forward + side * 0.25
      if (!inline || score < inline.score) inline = {el, score}
    } else {
      const score = forward + side * 3
      if (!loose || score < loose.score) loose = {el, score}
    }
  }
  return (inline || loose)?.el || null
}

export function createSpatial(sdk) {
  const {useEffect, useRef} = sdk.ui

  /**
   * @param root      ref to the screen's element
   * @param opts.allowed()      true while this screen owns the pad
   * @param opts.scope()        optional narrower element to move within
   * @param opts.initial        selector focused when nothing is remembered
   * @param opts.onFocus(el)    a control received focus (pad or pointer)
   * @param opts.edge(dir)      a step found nothing in that direction
   * @param opts.keys           {back, l1, r1, l2, r2, y, x, confirm}
   * @param watch               values that, when they change, re-focus
   */
  return function useSpatial(root, opts, watch = []) {
    const live = useRef(opts)
    live.current = opts
    const memory = useRef(null)
    // True while focus sits where restore() put it rather than where the
    // player moved it: a screen still loading may offer a better start later.
    const auto = useRef(false)
    const restoring = useRef(false)
    const depth = sdk.nav.use((s) => s.modalDepth)
    const screen = sdk.nav.use((s) => s.screen)

    const scope = () => live.current.scope?.() || root.current
    const items = () => [...(scope()?.querySelectorAll('[data-nav]') || [])].filter(visible)

    const focus = (el) => {
      if (!el) return
      auto.current = restoring.current
      el.focus({preventScroll: true})
      try { el.scrollIntoView({block: 'nearest', inline: 'nearest'}) } catch { /* jsdom */ }
    }

    /** Back where the player left, or the screen's starting point. */
    const restore = (again = false) => {
      const s = scope()
      if (!s) return
      if (!again && s.contains(document.activeElement) && document.activeElement !== s) return
      const remembered = !again && memory.current
        && [...s.querySelectorAll('[data-nav]')].find((el) => el.dataset.nav === memory.current)
      const start = remembered && visible(remembered) ? remembered
        : (live.current.initial && [...s.querySelectorAll(live.current.initial)].find(visible)) || items()[0]
      restoring.current = true
      focus(start)
      restoring.current = false
    }

    // Remember what has focus, whichever way it got there.
    useEffect(() => {
      const el = root.current
      if (!el) return
      const onIn = (e) => {
        const target = e.target.closest?.('[data-nav]')
        if (!target || !el.contains(target)) return
        if (!restoring.current) auto.current = false
        memory.current = target.dataset.nav
        live.current.onFocus?.(target)
      }
      el.addEventListener('focusin', onIn)
      return () => el.removeEventListener('focusin', onIn)
    }, [root.current])

    useEffect(() => {
      if (live.current.allowed()) restore()
    }, [depth, screen])
    // The screen filled in (a list loaded, a filter changed): a start that was
    // only a stand-in moves to the real one; a place the player chose stays.
    useEffect(() => {
      if (live.current.allowed()) restore(auto.current)
    }, watch)

    useEffect(() => {
      watchPresses(sdk)
      const move = (dir) => {
        if (!live.current.allowed()) return
        const s = scope()
        const from = s?.contains(document.activeElement) ? document.activeElement : null
        if (!from || !from.matches('[data-nav]')) { restore(); return }
        const to = nextInDirection(from, items(), DIRS[dir])
        if (to) { sdk.system.playSound('move'); focus(to) } else live.current.edge?.(dir)
      }
      const key = (name) => () => {
        if (!live.current.allowed()) return
        live.current.keys?.[name]?.()
      }
      const offs = [
        ...Object.keys(DIRS).map((d) => sdk.input.onGp(`gp:dpad-${d}`, () => move(d))),
        sdk.input.onGp('gp:confirm', () => {
          if (!live.current.allowed()) return
          const el = document.activeElement
          if (scope()?.contains(el) && el.matches('[data-nav]')) el.click()
          else live.current.keys?.confirm?.()
        }),
        ...['back', 'l1', 'r1', 'l2', 'r2', 'y', 'x'].map((n) => sdk.input.onGp(`gp:${n}`, key(n))),
      ]
      return () => offs.forEach((off) => off())
    }, [])

    return {restore, focus, forget: () => { memory.current = null }}
  }
}

const now = (sdk) => ({...sdk.nav.get(), transition: sdk.nav.use.getState?.().transition ?? null})

/**
 * The store as it was when the current press began.
 *
 * One press reaches every listener, the host's and Jelly's, in turn. When the
 * host's ○ takes the library home, a Jelly listener later in the line would
 * otherwise read `screen: 'home'` and act on the same press a second time
 * (leaving Consoles for Play). A capturing listener runs before all of them
 * and keeps the state they should all judge the press by; it is cleared once
 * the dispatch is over.
 */
let pressed = null
let watching = false
export function watchPresses(sdk) {
  if (watching || typeof window === 'undefined') return
  watching = true
  for (const name of sdk.input.events || []) {
    window.addEventListener(name, () => {
      pressed = now(sdk)
      queueMicrotask(() => { pressed = null })
    }, {capture: true})
  }
}
export const navAtPress = (sdk) => pressed || now(sdk)

/** The press being dispatched right now, or null between presses. A new
 * object per press, so a value read once per press can be keyed on it. */
export const currentPress = () => pressed

/** The launch flag. `nav.get()` leaves it out; `nav.use` is the store hook
 * itself, which carries `getState`. */
export const launching = (sdk) => navAtPress(sdk).transition === 'launch'

/** The pad belongs to the dashboard: nothing above it, no game, no launch. */
export const homeOwnsPad = (sdk) => {
  const s = navAtPress(sdk)
  return s.screen === 'home' && !s.modalDepth && !s.sessionGameKey
    && s.transition !== 'launch' && !s.powerPending && s.standby === 'off'
}

/** The pad belongs to the library screen, and nothing is over it. */
export const libraryOwnsPad = (sdk) => {
  const s = navAtPress(sdk)
  return s.screen === 'library' && !s.modalDepth && !s.sessionGameKey
    && s.transition !== 'launch' && !s.powerPending && s.standby === 'off'
}

/** The pad belongs to a layer opened at this modal depth, and nothing above it. */
export const layerOwnsPad = (sdk, depth) => {
  const s = navAtPress(sdk)
  return depth > 0 && s.modalDepth === depth && !s.sessionGameKey
    && !s.powerPending && s.standby === 'off'
}
