import {watchPresses} from './presses.js'

/** Pad navigation over the `[data-nav]` controls on screen: the d-pad moves
 * DOM focus by position, ✕ clicks the focused one. Repeat, stick and dead
 * zones are the host bus's; this only decides where a step lands. */
const DIRS = {left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1]}
const KEYS = ['back', 'l1', 'r1', 'l2', 'r2', 'y', 'x']
// Pixels of overlap or travel below which two boxes count as touching.
const SLACK = 2
// In line, sideways distance barely matters; off line, it costs three times.
const INLINE_SIDE_WEIGHT = 0.25
const LOOSE_SIDE_WEIGHT = 3

// jsdom reports no boxes at all; there, anything enabled counts as shown.
const laidOut = () => document.documentElement.getClientRects().length > 0
const visible = (el) => !el.disabled && el.getAttribute('aria-disabled') !== 'true'
  && (el.getClientRects().length > 0 || !laidOut())

/** The next control in a direction. One in line (same row or column) wins over
 * a closer one off to the side, so a step never goes diagonal needlessly. */
export function nextInDirection(from, items, [dx, dy]) {
  const a = from.getBoundingClientRect()
  const ax = (a.left + a.right) / 2
  const ay = (a.top + a.bottom) / 2
  let inline = null
  let loose = null
  for (const el of items) {
    if (el === from) continue
    const b = el.getBoundingClientRect()
    const forward = dx * ((b.left + b.right) / 2 - ax) + dy * ((b.top + b.bottom) / 2 - ay)
    if (forward <= SLACK) continue
    const side = Math.abs(dy * ((b.left + b.right) / 2 - ax) + dx * ((b.top + b.bottom) / 2 - ay))
    const overlaps = dx ? b.top < a.bottom - SLACK && b.bottom > a.top + SLACK
      : b.left < a.right - SLACK && b.right > a.left + SLACK
    const score = forward + side * (overlaps ? INLINE_SIDE_WEIGHT : LOOSE_SIDE_WEIGHT)
    if (overlaps && (!inline || score < inline.score)) inline = {el, score}
    if (!overlaps && (!loose || score < loose.score)) loose = {el, score}
  }
  return (inline || loose)?.el || null
}

/** The nearest ancestor that scrolls, or null. */
const scrollerOf = (el) => {
  for (let p = el.parentElement; p; p = p.parentElement) {
    if (/(auto|scroll)/.test(getComputedStyle(p).overflowY)) return p
  }
  return null
}

/** A step stays in the scrolled list it starts in while that list has
 * something that way. Rows scrolled out of view keep their boxes above the
 * list, past the controls over it, so geometry alone would jump out early. */
export function stepFrom(from, items, dir) {
  const box = scrollerOf(from)
  const inside = box ? items.filter((el) => box.contains(el)) : []
  return (inside.length && nextInDirection(from, inside, dir)) || nextInDirection(from, items, dir)
}

export function createSpatial(sdk) {
  const {useEffect, useRef} = sdk.ui

  /** Where focus was, and putting it back. `auto` marks a start restore() chose,
   * which a screen that fills in later may replace; a player's choice stays. */
  function useFocusMemory(root, live) {
    const memory = useRef(null)
    const auto = useRef(false)
    const restoring = useRef(false)
    const items = () => [...(root.current?.querySelectorAll('[data-nav]') || [])].filter(visible)
    const focus = (el) => {
      if (!el) return
      auto.current = restoring.current
      el.focus({preventScroll: true})
      try { el.scrollIntoView({block: 'nearest', inline: 'nearest'}) } catch { /* jsdom */ }
    }
    const restore = (again = false) => {
      const s = root.current
      if (!s || (!again && s.contains(document.activeElement) && document.activeElement !== s)) return
      const remembered = !again && items().find((el) => el.dataset.nav === memory.current)
      const initial = live.current.initial && [...s.querySelectorAll(live.current.initial)].find(visible)
      restoring.current = true
      focus(remembered || initial || items()[0])
      restoring.current = false
    }
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
    return {items, focus, restore, auto}
  }

  /**
   * One screen's pad: `opts.allowed()` while it owns the pad, `opts.initial` a
   * selector to start on, `opts.onFocus(el)`, `opts.keys` {back, l1, r1, l2, r2,
   * y, x, confirm}. `watch` values re-place a start the player never moved.
   */
  return function useSpatial(root, opts, watch = []) {
    const live = useRef(opts)
    live.current = opts
    const {items, focus, restore, auto} = useFocusMemory(root, live)
    const depth = sdk.nav.use((s) => s.modalDepth)
    const screen = sdk.nav.use((s) => s.screen)
    useEffect(() => { if (live.current.allowed()) restore() }, [depth, screen])
    useEffect(() => { if (live.current.allowed()) restore(auto.current) }, watch)

    useEffect(() => {
      watchPresses(sdk)
      const mine = () => live.current.allowed()
      const move = (dir) => {
        const from = root.current?.contains(document.activeElement) ? document.activeElement : null
        if (!from?.matches('[data-nav]')) { restore(); return }
        const to = stepFrom(from, items(), DIRS[dir])
        if (to) { sdk.system.playSound('move'); focus(to) }
      }
      const confirm = () => {
        const el = document.activeElement
        if (root.current?.contains(el) && el.matches('[data-nav]')) el.click()
        else live.current.keys?.confirm?.()
      }
      const offs = [
        ...Object.keys(DIRS).map((d) => sdk.input.onGp(`gp:dpad-${d}`, () => { if (mine()) move(d) })),
        sdk.input.onGp('gp:confirm', () => { if (mine()) confirm() }),
        ...KEYS.map((n) => sdk.input.onGp(`gp:${n}`, () => { if (mine()) live.current.keys?.[n]?.() })),
      ]
      return () => offs.forEach((off) => off())
    }, [])
  }
}
