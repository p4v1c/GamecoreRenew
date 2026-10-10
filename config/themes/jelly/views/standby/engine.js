import {stepBodies, squashScale, outline, findSpawn, driftVelocity} from '../../lib/standby/physics.js'
import {createDirector, createDeck, showSeconds, GATHER_S, RELEASE_S, STILL_S} from '../../lib/standby/director.js'
import {PALETTE, createBlobEl, sizeBlobEl, coverLoads, splatAt} from './blob.js'
import {createFeatureMedia} from './media.js'

// Everything below in pixels of the 1920x1080 design, scaled by `unit`.
const DESIGN_W = 1920
const DESIGN_H = 1080
/** Jelly diameters, the mockup's seven. */
const SIZES = [380, 520, 400, 300, 260, 300, 240]
const SPEED = {min: 28, max: 54}
/** The featured jelly: centred above the caption and the clock. */
const FEATURE = {x: 960, y: 420, w: 860, h: 600}
/** The soft field starts this far from the caption and the clock; the hard
 * wall stands at GUARD, past the outline's wobble. */
const ZONE_MARGIN = 72
const ZONE_GUARD = 24

const ENTER_S = 0.9
const POP_S = 0.28
const DT_MAX = 0.05
/** The outline is a repaint, so it breathes at 30 Hz; transforms run every frame. */
const MORPH_EVERY_S = 1 / 30
const MORPH_AMP = 9
const FEATURE_MORPH_AMP = 4
const REDUCED_TICK_MS = 250
const REDUCED_FADE_S = 0.6
const REDUCED_LEAVE_MS = 650
/** How much of its radius a still jelly may overlap another by. */
const REDUCED_MAX_OVERLAP = 0.1

const easeOutBack = (k) => 1 + 2.6 * Math.pow(k - 1, 3) + 1.6 * Math.pow(k - 1, 2)
const easeInOut = (k) => (k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2)
/** 0 → 1 with a jelly's overshoot and settle. */
const wobbleIn = (k) => (k >= 1 ? 1 : 1 - Math.pow(2, -9 * k) * Math.cos(k * Math.PI * 3.2))

/**
 * The standby's jellies: one frame loop that steps the physics, runs the
 * director's timeline and writes each jelly's transform. No layout is read
 * per frame; sizes change only when a feature starts or ends. Under reduced
 * motion there is no loop: jellies sit still, a pop is a fade, and the
 * featured game fades in on a still jelly at the centre.
 */
export function createEngine({root, layer, games, reel, reduced, onCaption, rand = Math.random}) {
  const deck = createDeck(games, rand)
  const director = createDirector(rand, reduced ? {gather: REDUCED_FADE_S, release: REDUCED_FADE_S} : {})
  const media = createFeatureMedia()
  const bodies = []
  const pending = new Set()
  let unit = 1
  let world = {w: DESIGN_W, h: DESIGN_H, zones: [], speed: SPEED}
  let zoneRects = []
  let t = 0
  let last = null
  let morphLeft = 0
  let raf = 0
  let timer = 0
  let dealt = 0
  let reelAt = 0
  let featured = null
  let stage = null
  let stopped = false

  const featureRect = () => ({x: FEATURE.x * unit, y: FEATURE.y * unit, w: FEATURE.w * unit, h: FEATURE.h * unit})

  function measure() {
    const box = root.getBoundingClientRect()
    // A root with no layout yet (a test, a hidden window): the design size.
    const w = box.width || DESIGN_W
    const h = box.height || DESIGN_H
    unit = Math.min(w / DESIGN_W, h / DESIGN_H)
    world = {w, h, zones: world.zones, speed: {min: SPEED.min * unit, max: SPEED.max * unit}}
    setZones(zoneRects)
  }

  /** Keep the jellies out of these rects (root-relative): the caption and
   * the clock. Under reduced motion the centre stage is one more. */
  function setZones(rects) {
    zoneRects = rects
    const margin = ZONE_MARGIN * unit
    const guard = ZONE_GUARD * unit
    const zones = rects.map((r) => ({...r, margin, guard}))
    if (reduced) {
      const f = featureRect()
      zones.push({left: f.x - f.w / 2, right: f.x + f.w / 2, top: f.y - f.h / 2, bottom: f.y + f.h / 2, margin, guard})
    }
    world = {...world, zones}
  }

  // Popping jellies count too: the game that just popped is not dealt straight back.
  const onScreen = () => new Set([...bodies.map((b) => b.game.key), ...pending])

  /** A spot and size for a new jelly. Still jellies never push each other
   * apart, so under reduced motion one that would overlap shrinks, up to
   * twice, then is not placed. */
  function place(d, at) {
    if (at) return {pos: at, d}
    for (const k of reduced ? [1, 0.8, 0.64] : [1]) {
      const spot = findSpawn(bodies, world, (d * k) / 2, rand)
      if (!reduced || spot.room >= (-REDUCED_MAX_OVERLAP * d * k) / 2) return {pos: {x: spot.x, y: spot.y}, d: d * k}
    }
    return null
  }

  function addBody(game, at) {
    const n = dealt++
    const spot = place(SIZES[n % SIZES.length] * unit, at)
    if (!spot) return null
    const {pos, d} = spot
    const color = PALETTE[n % PALETTE.length]
    const el = createBlobEl(game, color, d)
    const v = reduced ? {vx: 0, vy: 0} : driftVelocity(world.speed, rand)
    const b = {game, color, el, d, elW: d, elH: d, vw: d, vh: d, r: d / 2, ...pos, ...v,
      sq: 0, sqa: 0, phase: rand() * 6, born: t, popAt: null, tween: null, pinned: false}
    if (reduced) {
      el.classList.add('is-still')
      el.style.borderRadius = outline(b.phase, 0, MORPH_AMP)
    }
    layer.appendChild(el)
    bodies.push(b)
    render(b)
    return b
  }

  /** The next game with a cover, as a new jelly; null when none is left. */
  async function deal(at, exclude = onScreen()) {
    for (let tries = 0; tries < 8; tries++) {
      const game = deck.next(exclude)
      if (!game) return null
      pending.add(game.key)
      const ok = await coverLoads(game)
      pending.delete(game.key)
      if (stopped) return null
      if (ok) return addBody(game, at)
      deck.drop(game.key)
    }
    return null
  }

  function pop(b) {
    b.popAt = t
    b.pinned = true
    if (reduced) {
      b.el.classList.add('is-leaving')
      setTimeout(() => remove(b), REDUCED_LEAVE_MS)
    } else {
      splatAt(layer, b.x, b.y, (b.vw / 2) * 1.1, b.color)
    }
  }

  function remove(b) {
    const i = bodies.indexOf(b)
    if (i >= 0) bodies.splice(i, 1)
    b.el.remove()
  }

  function popOne() {
    const choices = bodies.filter((b) => b.popAt === null && b !== featured?.body && t - b.born > ENTER_S)
    if (!choices.length) return
    const b = choices[Math.floor(rand() * choices.length)]
    pop(b)
    // Another game wobbles in; the popped one only when nothing else is left.
    deal().then((nb) => nb || deal(undefined, new Set([...onScreen()].filter((k) => k !== b.game.key))))
      .then((nb) => { if (nb && !featured) onCaption(nb.game) })
  }

  /** The next thing to feature: the reel's next clip or still, else the
   * cover of a jelly already on screen. */
  function nextEntry() {
    if (reel.length) return reel[reelAt++ % reel.length]
    const live = bodies.filter((b) => b.popAt === null)
    if (!live.length) return null
    return {kind: 'cover', game: live[Math.floor(rand() * live.length)].game}
  }

  const mediaEvents = {
    onLength: (s) => director.showFor(showSeconds('video', s)),
    onEnd: () => director.endShow(t),
  }

  function gather() {
    const entry = nextEntry()
    if (!entry) return
    onCaption(entry.game)
    if (reduced) {
      stage = stage || createStage()
      media.load(stage.el, entry, mediaEvents)
      stage.el.classList.add('is-on')
      featured = {body: stage, entry}
      return
    }
    const body = bodies.find((b) => b.popAt === null && b.game.key === entry.game.key) || replaceNearCentre(entry.game)
    if (!body) return
    const f = featureRect()
    sizeBlobEl(body.el, f.w, f.h)
    body.elW = f.w
    body.elH = f.h
    body.el.classList.add('is-big')
    body.pinned = true
    body.tween = tweenOf(body, {x: f.x, y: f.y, vw: f.w, vh: f.h}, GATHER_S, easeOutBack)
    media.load(body.el, entry, mediaEvents)
    featured = {body, entry}
  }

  /** A featured game with no jelly yet: the jelly nearest the centre pops
   * and the game wobbles in where it was. */
  function replaceNearCentre(game) {
    const f = featureRect()
    const live = bodies.filter((b) => b.popAt === null && t - b.born > ENTER_S)
    const near = live.sort((a, c) => Math.hypot(a.x - f.x, a.y - f.y) - Math.hypot(c.x - f.x, c.y - f.y))[0]
    if (near) pop(near)
    return addBody(game, near ? {x: near.x, y: near.y} : {x: f.x, y: f.y})
  }

  function createStage() {
    const f = featureRect()
    const el = createBlobEl(null, PALETTE[0], f.w)
    sizeBlobEl(el, f.w, f.h)
    el.classList.add('jl-sb-stage', 'is-still')
    el.style.borderRadius = outline(0, 0, FEATURE_MORPH_AMP)
    el.style.transform = `translate3d(${f.x - f.w / 2}px, ${f.y - f.h / 2}px, 0)`
    layer.appendChild(el)
    return {el}
  }

  const tweenOf = (b, to, dur, ease) => ({t0: t, dur, ease, to, from: {x: b.x, y: b.y, vw: b.vw, vh: b.vh}})

  function show() {
    if (!featured) return
    media.show()
    if (featured.entry.kind !== 'video') director.showFor(STILL_S)
  }

  function release() {
    if (!featured) return
    media.hide()
    if (reduced) { stage.el.classList.remove('is-on'); return }
    const b = featured.body
    b.tween = tweenOf(b, {x: b.x, y: b.y, vw: b.d, vh: b.d}, RELEASE_S, easeInOut)
  }

  function settle() {
    media.release()
    const b = featured?.body
    featured = null
    if (!b || reduced) return
    b.tween = null
    sizeBlobEl(b.el, b.d, b.d)
    b.el.classList.remove('is-big')
    b.elW = b.elH = b.vw = b.vh = b.d
    b.pinned = false
    Object.assign(b, driftVelocity(world.speed, rand))
  }

  const ACTIONS = {gather, show, release, settle, pop: popOne}

  function act() {
    for (const a of director.tick(t)) ACTIONS[a]()
    // Read by the capture tools; written only on a change, never per frame.
    if (root.dataset.phase !== director.phase()) root.dataset.phase = director.phase()
  }

  function advanceTween(b) {
    const k = Math.min(1, (t - b.tween.t0) / b.tween.dur)
    const e = b.tween.ease(k)
    for (const p of ['x', 'y', 'vw', 'vh']) b[p] = b.tween.from[p] + (b.tween.to[p] - b.tween.from[p]) * e
    if (k >= 1) b.tween = null
  }

  /** Size, enter and pop as one scale; squash along its axis on top. */
  function render(b) {
    let s = 1
    if (!reduced) {
      const age = t - b.born
      if (age < ENTER_S) s = Math.max(0.001, wobbleIn(age / ENTER_S))
      if (b.popAt !== null) {
        const k = Math.min(1, (t - b.popAt) / POP_S)
        s *= 1 + 0.25 * k
        b.el.style.opacity = String(1 - k)
      }
    }
    b.r = Math.max(1, ((b.vw + b.vh) / 4) * Math.min(1, s))
    const q = reduced ? {sx: 1, sy: 1, angle: 0} : squashScale(b, t)
    b.el.style.transform = `translate3d(${b.x - b.elW / 2}px, ${b.y - b.elH / 2}px, 0) `
      + `rotate(${q.angle}rad) scale(${q.sx}, ${q.sy}) rotate(${-q.angle}rad) `
      + `scale(${(b.vw / b.elW) * s}, ${(b.vh / b.elH) * s})`
  }

  function frame(now) {
    const dt = last === null ? 0 : Math.min(DT_MAX, (now - last) / 1000)
    last = now
    t += dt
    act()
    for (const b of [...bodies]) {
      if (b.tween) advanceTween(b)
      if (b.popAt !== null && t - b.popAt >= POP_S) remove(b)
    }
    stepBodies(bodies.filter((b) => b.popAt === null), dt, world)
    morphLeft -= dt
    const morph = morphLeft <= 0
    if (morph) morphLeft = MORPH_EVERY_S
    for (const b of bodies) {
      if (morph) b.el.style.borderRadius = outline(b.phase, t, b === featured?.body ? FEATURE_MORPH_AMP : MORPH_AMP)
      render(b)
    }
    raf = requestAnimationFrame(frame)
  }

  /** Deal until the floor holds its jellies (fewer when the library is small). */
  async function fill() {
    const missing = SIZES.length - bodies.filter((b) => b.popAt === null).length - pending.size
    const dealtNow = await Promise.all(Array.from({length: Math.max(0, missing)}, () => deal()))
    const shown = dealtNow.find(Boolean)
    if (shown && !featured && !stopped) onCaption(shown.game)
  }

  async function start() {
    measure()
    await fill()
    if (stopped) return
    if (reduced) timer = setInterval(() => { t += REDUCED_TICK_MS / 1000; act() }, REDUCED_TICK_MS)
    else raf = requestAnimationFrame(frame)
  }

  function stop() {
    stopped = true
    cancelAnimationFrame(raf)
    clearInterval(timer)
    media.release()
    layer.replaceChildren()
    bodies.length = 0
  }

  /** More games for the deck; empty places on the floor fill at once. */
  function addGames(more) {
    if (stopped || !more.length) return
    deck.add(more)
    fill()
  }

  return {start, stop, setZones, measure, addGames}
}
