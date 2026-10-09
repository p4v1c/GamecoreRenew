/**
 * The jacket swap, as a motion that can be interrupted.
 *
 * Moving along the shelf puts the box in your hand back into the row and takes
 * the next one out. That used to be two CSS keyframe animations on two keyed
 * holders, and keyframes cannot be interrupted: a press in the middle of one
 * could only cancel it, so the view did — the jacket vanished mid-turn, and
 * while presses kept arriving faster than the 360 ms put-back, no jacket ever
 * came out at all. On a d-pad held or tapped at an ordinary pace that was most
 * of the time: the animation the shelf exists for was the thing you saw least.
 *
 * Here every jacket on stage is one number, `p`:
 *
 *     p = 0   in your hand, turned towards you (the resting pose css/library-
 *             motion.css declares, so at rest the CSS owns it again)
 *     p = 1   back in the row: edge-on, at the row's depth, in its own column,
 *             at that column's lean — pixel for pixel the spine standing there
 *
 * The jacket under the cursor heads for 0, every other one heads for 1, every
 * frame. Changing your mind is therefore never a cut: a box half way out simply
 * starts going back from exactly where it is, and the new one comes out after
 * it. The first half of the travel is the turn (0 → 0.5), the second the move
 * into the row (0.5 → 1), the same two gestures, in the same order, as before.
 *
 * Speed follows the hand. At a resting pace the put-back takes 360 ms and the
 * take-out 560 ms, one strictly after the other, which is the original
 * ceremony. Pressing faster shortens both, down to a third, and lets the
 * next jacket start out while the last is still sliding home — so a burst on
 * the d-pad is a quick ripple of boxes going back and coming out, never a jump.
 *
 * The column a returning box lands in is read off the rail itself (its live,
 * mid-transition transform), not computed from the index, so a box sent back
 * while the rail is still sliding lands where its spine actually is.
 *
 * Transforms are written straight to the elements from requestAnimationFrame.
 * React only learns which jackets exist, so a frame of motion costs no render.
 */
import { jacket } from './dossier.js'

const PUSH_MS = 360          // put back, at rest
const PULL_MS = 560          // take out, at rest
const FASTEST = 3            // the most a burst may speed it up
const CATCH_UP = 1.2         // extra, for a box put away while the next one waits
const STEP_MS = 34           // the longest frame the motion will take in one step
/** The most of a gesture one drawn frame may cover, so even the fastest put-back
 *  is seen on eight frames or more rather than as a hop. */
const MAX_DP = 0.12
/** One whole swap at rest: the put-back up to its hand-over point, then the
 *  take-out. Presses closer together than this get a swap that fits between
 *  them, so up to about four presses a second every box still turns to face
 *  you; only faster than FASTEST allows does one turn back before it has. */
const SWAP_MS = PUSH_MS * 0.55 + PULL_MS

/** Ease both ways: the motion reverses mid-flight, so neither end is special. */
const ease = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t))
const seg = (p, a, b) => ease((p - a) / (b - a))

const num = (v, fallback = 0) => {
  const n = parseFloat(v)
  return Number.isFinite(n) ? n : fallback
}

/** The rail's live position in columns, read from its (transitioning) transform. */
const railAt = (rail, stack) => {
  if (!rail) return null
  const cs = getComputedStyle(rail)
  const pitch = num(cs.getPropertyValue('--pitch'), 40)
  const m = cs.transform
  if (!m || m === 'none') return 0
  const v = m.match(/matrix(3d)?\((.+)\)/)
  if (!v) return 0
  const a = v[2].split(',').map(Number)
  const t = v[1] ? (stack ? a[13] : a[12]) : (stack ? a[5] : a[4])
  return -t / pitch
}

export const createUseSwap = (sdk) => {
  const { useState, useEffect, useRef } = sdk.ui

  return ({ systemId, games, selectedIdx, mode, flipped, railRef, lean }) => {
    const target = games[selectedIdx]?.filename || null
    const stack = mode === 'stack'

    // Which jackets exist is React state; where each one is lives here.
    const [keys, setKeys] = useState([])
    const live = useRef(null)
    if (!live.current) {
      live.current = { jackets: new Map(), raf: 0, last: 0, presses: [], keys: [] }
    }
    const S = live.current
    S.games = games
    S.target = target
    S.stack = stack
    S.lean = lean
    S.railRef = railRef

    // The box in your hand carries its flip with it when it is put back, so a
    // reversed box turns home from its back rather than snapping to its front.
    const held = S.jackets.get(target)
    if (held && held.p === 0) held.flip = flipped ? 180 : 0

    const reduced = () => {
      try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch { return false }
    }

    /** How much faster than at rest, from the gap between the last presses. */
    const speed = (now) => {
      if (reduced()) return 60
      const ps = S.presses
      if (ps.length < 2 || now - ps[ps.length - 1] > SWAP_MS) return 1
      const gap = (ps[ps.length - 1] - ps[0]) / (ps.length - 1)
      return Math.max(1, Math.min(FASTEST, SWAP_MS / Math.max(40, gap)))
    }

    /** Write one jacket's pose. Its geometry is read once per stacking. */
    const apply = (j) => {
      const carry = j.carry
      const box = carry?.firstElementChild
      if (!carry || !box) return
      if (j.mode !== mode || !j.w) {
        const hold = carry.parentElement
        const bs = getComputedStyle(box), hs = getComputedStyle(hold)
        j.mode = mode
        j.w = num(bs.width, 300)
        j.turn = num(bs.getPropertyValue('--turn'), 25)
        j.tilt = num(bs.getPropertyValue('--tilt'), -5)
        j.dive = num(hs.getPropertyValue('--dive'), -425)
        j.slide = num(hs.getPropertyValue('--slide'), 50)
      }
      // At rest in the hand the stylesheet owns the pose (and the L2 flip's
      // transition); anywhere else this does, with the transition off so the
      // two never fight over the same property.
      if (j.p <= 0 && j.key === S.target) {
        if (j.driven) {
          carry.style.transform = ''
          box.style.transform = ''
          box.style.transition = ''
          j.driven = false
        }
        return
      }
      const r = seg(j.p, 0, 0.5)          // the turn
      const q = seg(j.p, 0.5, 1)          // the move into the row
      const at = railAt(S.railRef.current, S.stack)
      const idx = S.games.findIndex((g) => g.filename === j.key)
      const off = (idx < 0 || at == null) ? 0 : (idx - at) * j.slide
      const base = j.turn + (j.flip || 0)
      carry.style.transform = S.stack
        ? `translate3d(0px, ${off * q}px, ${j.dive * q}px)`
        : `translate3d(${off * q}px, 0px, ${j.dive * q}px) rotateZ(${(idx < 0 ? 0 : S.lean(idx)) * q}deg)`
      box.style.transition = 'width 300ms ease, height 300ms ease'
      box.style.transform = `translateZ(${(-j.w / 2) * r}px)`
        + (S.stack ? ` rotateZ(${-90 * r}deg)` : '')
        + ` rotateX(${j.tilt * (1 - r)}deg) rotateY(${base + (90 - base) * r}deg)`
      j.driven = true
    }

    const publish = () => {
      // The one in your hand is drawn last, so it is in front of the one going back.
      const next = [...S.jackets.keys()].sort((a, b) => (a === S.target) - (b === S.target))
      if (next.join('\n') !== S.keys.join('\n')) { S.keys = next; setKeys(next) }
    }

    const frame = (now) => {
      S.raf = 0
      // A dropped frame slows the motion down rather than skipping a stretch of it.
      const dt = Math.min(STEP_MS, S.last ? now - S.last : 16)
      S.last = now
      const k = speed(now)
      const t = S.target

      // A jacket that has left the shelf (a search narrowed it) has nowhere
      // to go back to; it is the one case that can only be removed.
      for (const [key, j] of S.jackets) {
        if (key !== t && !S.games.some((g) => g.filename === key)) S.jackets.delete(key)
      }

      // The next jacket comes out once the last is home — or, in a burst,
      // once it is turned edge-on and only sliding home.
      const others = [...S.jackets.values()].filter((j) => j.key !== t)
      const ready = others.every((j) => j.p >= (k > 1.15 ? 0.55 : 1))
      if (t && !S.jackets.has(t) && ready) S.jackets.set(t, { key: t, p: 1, flip: 0 })
      const waiting = t && !S.jackets.has(t)

      let moving = false
      for (const j of S.jackets.values()) {
        const home = j.key !== t
        // Someone is waiting to come out: put the last one away quicker.
        const rate = home ? (k * (waiting ? CATCH_UP : 1)) / PUSH_MS : k / PULL_MS
        j.p = Math.max(0, Math.min(1, j.p + (home ? 1 : -1) * Math.min(MAX_DP, rate * dt)))
        if (home ? j.p < 1 : j.p > 0) moving = true
        apply(j)
      }
      for (const [key, j] of S.jackets) if (key !== t && j.p >= 1) S.jackets.delete(key)
      publish()
      if (moving || waiting) S.raf = requestAnimationFrame(frame)
      else S.last = 0
    }

    const kick = () => {
      if (!S.raf) { S.last = 0; S.raf = requestAnimationFrame(frame) }
    }

    useEffect(() => {
      if (!target) return
      const now = performance.now()
      S.presses = [...S.presses.filter((t) => now - t < 1500), now].slice(-4)
      kick()
    }, [target])

    // A change of stacking moves the row and the hand; re-read both.
    useEffect(() => { S.jackets.forEach((j) => { j.mode = null; apply(j) }) }, [mode])
    useEffect(() => () => { if (S.raf) cancelAnimationFrame(S.raf) }, [])

    // Warm the neighbours once the cursor rests, so the next box out has its
    // front and back decoded before it turns to face you or is flipped. The
    // spine needs nothing: it is already standing in the row. A game with no
    // back scan answers 404 from its cached manifest, which costs nothing.
    useEffect(() => {
      const t = setTimeout(() => {
        for (const d of [1, -1, 2, -2]) {
          const g = games[selectedIdx + d]
          if (!g) continue
          for (const src of [jacket(systemId, g.filename),
            sdk.api.media.url(systemId, g.filename, 'box-back')]) {
            const img = new Image()
            img.decoding = 'async'
            img.src = src
          }
        }
      }, 400)
      return () => clearTimeout(t)
    }, [systemId, selectedIdx, games])

    /**
     * Ref for a jacket's `.cz-carry`. Runs at commit, before the browser
     * paints, so a jacket mounted at p = 1 is drawn as a spine on its very
     * first frame — the same frame its column in the row is hidden.
     */
    const bind = (key) => (el) => {
      const j = S.jackets.get(key)
      if (!j) return
      j.carry = el
      if (el) apply(j)
    }

    /** Is this game's column empty because its jacket is on stage? */
    const out = (filename) => S.jackets.has(filename)
    /** The flip a jacket carries (only the one in hand follows L2). */
    const flipOf = (key) => (key === target ? flipped : (S.jackets.get(key)?.flip || 0) === 180)

    return { keys, bind, out, flipOf }
  }
}
