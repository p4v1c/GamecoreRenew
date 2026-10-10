/** The standby jellies' physics, pure: no DOM, no clock. The swarm view
 * (views/standby/engine.js) owns the frame loop and the elements; this file
 * only moves numbers, so the tests can drive it frame by frame.
 *
 * A body: {x, y, vx, vy, r, sq, sqa, pinned?}, in screen pixels. `r` is the
 * collision radius; `sq` the squash left from the last impact and `sqa` its
 * axis. A pinned body (the featured jelly) is moved by its owner and has
 * infinite mass: the others bounce off it, it never moves for them. */

/** Bodies bounce once this share of their radius is past an edge, so a jelly
 * can hang off the screen a little, as in the mockup. */
export const EDGE_INSET = 0.6
/** Jellies are soft: they touch a little inside their drawn outline. */
export const CONTACT = 0.92
export const SQUASH_HIT = 0.16
export const SQUASH_EDGE = 0.14
/** What is left of a squash after one second. */
export const SQUASH_KEEP_PER_S = 0.02
/** The wobble's angular speed (rad/s): about 1.4 bounces a second. */
export const WOBBLE_RATE = 9
/** Repel zones push with this stiffness (1/s²) per pixel of intrusion. At the
 * fastest drift a jelly stops ~22 px inside the soft margin, then turns back. */
export const ZONE_STIFFNESS = 6
/** How fast a speed outside the drift band is eased back into it (1/s). */
export const SPEED_EASE = 1.5

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))

/** How a body leaves a zone: unit normal and depth, or null when clear.
 * A zone is {left, top, right, bottom, margin, guard}: the soft field reaches
 * `margin` past the rect, the hard wall `guard`. Measured from the drawn
 * outline (`r`), since what matters is the text staying uncovered. */
export function zoneIntrusion(b, z, extra = z.margin || 0) {
  const reach = b.r + extra
  const px = clamp(b.x, z.left, z.right)
  const py = clamp(b.y, z.top, z.bottom)
  const dx = b.x - px
  const dy = b.y - py
  const d = Math.hypot(dx, dy)
  if (d >= reach) return null
  if (d > 0) return {nx: dx / d, ny: dy / d, depth: reach - d}
  // The centre is inside the zone: leave by the nearest side.
  const exits = [
    [b.x - z.left, -1, 0], [z.right - b.x, 1, 0],
    [b.y - z.top, 0, -1], [z.bottom - b.y, 0, 1],
  ].sort((a, c) => a[0] - c[0])
  const [dist, nx, ny] = exits[0]
  return {nx, ny, depth: reach + dist}
}

function repel(b, zones, dt) {
  for (const z of zones) {
    const hit = zoneIntrusion(b, z)
    if (!hit) continue
    b.vx += hit.nx * ZONE_STIFFNESS * hit.depth * dt
    b.vy += hit.ny * ZONE_STIFFNESS * hit.depth * dt
  }
}

/** The hard wall behind the soft field: a crowd shoving a jelly toward the
 * text cannot push it past `guard`. It leaves sliding along the wall. */
function guard(b, zones) {
  for (const z of zones) {
    const hit = zoneIntrusion(b, z, z.guard || 0)
    if (!hit) continue
    b.x += hit.nx * hit.depth
    b.y += hit.ny * hit.depth
    const inward = b.vx * hit.nx + b.vy * hit.ny
    if (inward < 0) { b.vx -= inward * hit.nx; b.vy -= inward * hit.ny }
  }
}

/** Ease the speed back into [min, max] without touching the heading. */
function keepPace(b, speed, dt) {
  const s = Math.hypot(b.vx, b.vy)
  if (s < 1e-6) { b.vx = speed.min; b.vy = 0; return }
  const target = clamp(s, speed.min, speed.max)
  const next = s + (target - s) * Math.min(1, dt * SPEED_EASE)
  b.vx *= next / s
  b.vy *= next / s
}

function squash(b, amount, angle) {
  if (amount >= b.sq) { b.sq = amount; b.sqa = angle }
}

function bounceEdges(b, world) {
  const inset = b.r * EDGE_INSET
  if (b.x < inset || b.x > world.w - inset) {
    b.vx = b.x < inset ? Math.abs(b.vx) : -Math.abs(b.vx)
    b.x = clamp(b.x, inset, world.w - inset)
    squash(b, SQUASH_EDGE, 0)
  }
  if (b.y < inset || b.y > world.h - inset) {
    b.vy = b.y < inset ? Math.abs(b.vy) : -Math.abs(b.vy)
    b.y = clamp(b.y, inset, world.h - inset)
    squash(b, SQUASH_EDGE, Math.PI / 2)
  }
}

const inverseMass = (b) => (b.pinned ? 0 : 1 / (b.r * b.r))

/** Push two overlapping bodies apart and swap momentum along the contact
 * normal (elastic, mass by area). True when they were touching. */
export function collide(a, b) {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const d = Math.hypot(dx, dy) || 1e-6
  const reach = (a.r + b.r) * CONTACT
  if (d >= reach) return false
  const ia = inverseMass(a)
  const ib = inverseMass(b)
  if (ia + ib === 0) return true
  const nx = dx / d
  const ny = dy / d
  const push = (reach - d) / (ia + ib)
  a.x -= nx * push * ia; a.y -= ny * push * ia
  b.x += nx * push * ib; b.y += ny * push * ib
  const closing = (a.vx - b.vx) * nx + (a.vy - b.vy) * ny
  if (closing <= 0) return true
  const j = (2 * closing) / (ia + ib)
  a.vx -= j * ia * nx; a.vy -= j * ia * ny
  b.vx += j * ib * nx; b.vy += j * ib * ny
  const angle = Math.atan2(ny, nx)
  squash(a, SQUASH_HIT, angle)
  squash(b, SQUASH_HIT, angle)
  return true
}

/**
 * One frame. `world` is {w, h, zones, speed: {min, max}}; `dt` in seconds,
 * capped by the caller. Mutates the bodies: the loop runs at 60 Hz on a mini
 * PC, and a copy per frame would be garbage for nothing.
 */
export function stepBodies(bodies, dt, world) {
  for (const b of bodies) {
    if (!b.pinned) {
      repel(b, world.zones || [], dt)
      keepPace(b, world.speed, dt)
      b.x += b.vx * dt
      b.y += b.vy * dt
      bounceEdges(b, world)
    }
  }
  for (let i = 0; i < bodies.length; i++) {
    for (let k = i + 1; k < bodies.length; k++) collide(bodies[i], bodies[k])
  }
  for (const b of bodies) if (!b.pinned) guard(b, world.zones || [])
  const keep = Math.pow(SQUASH_KEEP_PER_S, dt)
  for (const b of bodies) b.sq *= keep
}

/** Squash as scale factors along the impact axis: a damped wobble. */
export function squashScale(b, t) {
  const w = Math.sin(t * WOBBLE_RATE + (b.phase || 0)) * b.sq
  return {sx: 1 + w, sy: 1 - w, angle: b.sqa}
}

/** The jelly's outline: eight border-radius values breathing around 50 %. */
export function outline(phase, t, amp) {
  const v = (k) => `${(50 + Math.sin(t * 1.3 + phase + k) * amp).toFixed(1)}%`
  return `${v(0)} ${v(1)} ${v(2)} ${v(3)} / ${v(4)} ${v(5)} ${v(6)} ${v(7)}`
}

/** Room left around a spot: distance to the nearest body, edge or zone. */
function clearance(x, y, r, bodies, world) {
  let room = Math.min(x, y, world.w - x, world.h - y) + r * (1 - EDGE_INSET)
  for (const b of bodies) room = Math.min(room, Math.hypot(b.x - x, b.y - y) - b.r)
  for (const z of world.zones || []) {
    const hit = zoneIntrusion({x, y, r: 0}, {...z, margin: 0})
    const d = hit ? -hit.depth : Math.hypot(x - clamp(x, z.left, z.right), y - clamp(y, z.top, z.bottom))
    room = Math.min(room, d - (z.margin || 0))
  }
  return room - r
}

/** Where a new jelly of radius `r` wobbles in: the roomiest of `tries`
 * random spots, with its `room` (negative: it would overlap by that much).
 * `rand` returns [0, 1), injected for the tests. */
export function findSpawn(bodies, world, r, rand, tries = 24) {
  let best = {x: world.w / 2, y: world.h / 2, room: -Infinity}
  for (let i = 0; i < tries; i++) {
    const x = r * EDGE_INSET + rand() * (world.w - 2 * r * EDGE_INSET)
    const y = r * EDGE_INSET + rand() * (world.h - 2 * r * EDGE_INSET)
    const room = clearance(x, y, r, bodies, world)
    if (room > best.room) best = {x, y, room}
  }
  return best
}

/** A drift velocity in the band, in a random heading. */
export function driftVelocity(speed, rand) {
  const a = rand() * Math.PI * 2
  const s = speed.min + rand() * (speed.max - speed.min)
  return {vx: Math.cos(a) * s, vy: Math.sin(a) * s}
}
