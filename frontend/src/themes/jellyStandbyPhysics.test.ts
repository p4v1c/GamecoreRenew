/**
 * Jelly's standby, the pure part: the jellies' physics (edges, collisions,
 * repel zones, squash) and the timeline (deck, feature reel, pops). The
 * frame loop and the DOM are covered by jellyStandby.test.tsx.
 */
import { beforeAll, describe, expect, it } from 'vitest'

const LIB = '../../../config/themes/jelly/lib/standby'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Mod = Record<string, any>
let physics: Mod
let director: Mod

beforeAll(async () => {
  physics = await import(/* @vite-ignore */ `${LIB}/physics.js`)
  director = await import(/* @vite-ignore */ `${LIB}/director.js`)
})

const SPEED = { min: 28, max: 54 }
const world = (zones: unknown[] = []) => ({ w: 1920, h: 1080, zones, speed: SPEED })
const body = (o: Record<string, number | boolean>): Mod => ({ x: 0, y: 0, vx: 0, vy: 0, r: 100, sq: 0, sqa: 0, ...o })
/** A seeded generator, so a failure replays. */
const seeded = (seed = 7) => () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646 }
const run = (bodies: unknown[], w: unknown, seconds: number, dt = 1 / 60) => {
  for (let t = 0; t < seconds; t += dt) physics.stepBodies(bodies, dt, w)
}

describe('jelly physics', () => {
  it('bounces off an edge once past the inset, and squashes along it', () => {
    const b = body({ x: 60.5, y: 500, vx: -50 })
    physics.stepBodies([b], 1 / 60, world())
    expect(b.vx).toBeGreaterThan(0)
    expect(b.x).toBeGreaterThanOrEqual(100 * physics.EDGE_INSET)
    expect(b.sq).toBeGreaterThan(0.1)
    expect(b.sqa).toBe(0)
  })

  it('bounces off the floor with the squash turned a quarter', () => {
    const b = body({ x: 900, y: 1075, vy: 50 })
    physics.stepBodies([b], 0.05, world())
    expect(b.vy).toBeLessThan(0)
    expect(b.sqa).toBeCloseTo(Math.PI / 2)
  })

  it('collides elastically: equal jellies head-on swap velocities', () => {
    const a = body({ x: 500, y: 500, vx: 40 })
    const b = body({ x: 680, y: 500, vx: -40 })
    expect(physics.collide(a, b)).toBe(true)
    expect(a.vx).toBeCloseTo(-40)
    expect(b.vx).toBeCloseTo(40)
    expect(Math.hypot(b.x - a.x, b.y - a.y)).toBeCloseTo(200 * physics.CONTACT)
    expect(a.sq).toBe(physics.SQUASH_HIT)
    expect(a.sqa).toBeCloseTo(0)
  })

  it('keeps momentum and energy when sizes differ', () => {
    const a = body({ x: 400, y: 400, r: 200, vx: 30, vy: 10 })
    const b = body({ x: 640, y: 420, r: 80, vx: -50, vy: 0 })
    const ma = a.r * a.r, mb = b.r * b.r
    const p0 = [ma * a.vx + mb * b.vx, ma * a.vy + mb * b.vy]
    const e0 = ma * (a.vx ** 2 + a.vy ** 2) + mb * (b.vx ** 2 + b.vy ** 2)
    physics.collide(a, b)
    expect(ma * a.vx + mb * b.vx).toBeCloseTo(p0[0], 3)
    expect(ma * a.vy + mb * b.vy).toBeCloseTo(p0[1], 3)
    expect(ma * (a.vx ** 2 + a.vy ** 2) + mb * (b.vx ** 2 + b.vy ** 2)).toBeCloseTo(e0, 0)
  })

  it('does not pull apart jellies that are already separating', () => {
    const a = body({ x: 500, y: 500, vx: -40 })
    const b = body({ x: 650, y: 500, vx: 40 })
    physics.collide(a, b)
    expect(a.vx).toBe(-40)
    expect(b.vx).toBe(40)
  })

  it('never moves a pinned jelly; the other one bounces off it', () => {
    const star = body({ x: 960, y: 500, r: 300, pinned: true })
    const b = body({ x: 960 + 300, y: 500, vx: -50 })
    physics.collide(star, b)
    expect(star.x).toBe(960)
    expect(b.vx).toBeCloseTo(50)
    expect(b.x).toBeCloseTo(960 + 400 * physics.CONTACT)
  })

  it('pushes a jelly out of a repel zone and keeps it out', () => {
    const zone = { left: 1400, top: 700, right: 1920, bottom: 1080, margin: 24 }
    const b = body({ x: 1100, y: 600, vx: 54, vy: 30 })
    const w = world([zone])
    let worst = Infinity
    for (let t = 0; t < 30; t += 1 / 60) {
      physics.stepBodies([b], 1 / 60, w)
      const hit = physics.zoneIntrusion(b, { ...zone, margin: 0 })
      worst = Math.min(worst, hit ? -hit.depth : 0)
    }
    // Soft: it may lean into the margin, never past it into the text.
    expect(worst).toBeGreaterThan(-zone.margin)
  })

  it('leaves a zone it starts inside by the nearest side', () => {
    const hit = physics.zoneIntrusion(body({ x: 1500, y: 1060 }), { left: 1400, top: 700, right: 1920, bottom: 1080 }, 0)
    expect(hit).toMatchObject({ nx: 0, ny: 1 })
  })

  it('eases any speed back into the drift band', () => {
    const fast = body({ x: 900, y: 500, vx: 400 })
    const still = body({ x: 300, y: 300 })
    run([fast], world(), 4)
    run([still], world(), 4)
    expect(Math.hypot(fast.vx, fast.vy)).toBeLessThan(SPEED.max + 1)
    expect(Math.hypot(still.vx, still.vy)).toBeGreaterThanOrEqual(SPEED.min - 1)
  })

  it('a swarm stays on screen and out of the zones for a minute', () => {
    const rand = seeded()
    const zones = [
      { left: 96, top: 830, right: 600, bottom: 1000, margin: 72, guard: 24 },
      { left: 1340, top: 740, right: 1810, bottom: 1000, margin: 72, guard: 24 },
    ]
    const w = world(zones)
    const bodies: Mod[] = []
    for (const r of [190, 260, 200, 150, 130, 150, 120]) {
      const at = physics.findSpawn(bodies, w, r, rand)
      bodies.push(body({ ...at, ...physics.driftVelocity(SPEED, rand), r }))
    }
    let intrusion = 0
    for (let t = 0; t < 60; t += 1 / 60) {
      physics.stepBodies(bodies, 1 / 60, w)
      for (const b of bodies) {
        expect(b.x).toBeGreaterThanOrEqual(b.r * physics.EDGE_INSET - 1e-6)
        expect(b.x).toBeLessThanOrEqual(1920 - b.r * physics.EDGE_INSET + 1e-6)
        for (const z of zones) {
          const hit = physics.zoneIntrusion(b, z, 0)
          if (hit) intrusion = Math.max(intrusion, hit.depth)
        }
      }
    }
    // The hard wall holds: no outline ever reaches the caption or the clock.
    expect(intrusion).toBe(0)
  })

  it('a pinned jelly cannot shove another into a zone: the wall wins', () => {
    const zone = { left: 1400, top: 700, right: 1920, bottom: 1080, margin: 72, guard: 24 }
    const star = body({ x: 1100, y: 500, r: 300, pinned: true })
    const b = body({ x: 1330, y: 640, r: 120, vx: 54, vy: 40 })
    for (let t = 0; t < 5; t += 1 / 60) {
      star.x += 0.5
      physics.stepBodies([star, b], 1 / 60, world([zone]))
      expect(physics.zoneIntrusion(b, zone, 0)).toBeNull()
    }
  })

  it('the squash dies down, wobbling around rest', () => {
    const b = body({ x: 900, y: 500, sq: 0.16, phase: 0 })
    const seen = new Set<number>()
    for (let t = 0; t < 1; t += 1 / 60) {
      physics.stepBodies([b], 1 / 60, world())
      seen.add(Math.sign(physics.squashScale(b, t).sx - 1))
    }
    expect(seen.has(1) && seen.has(-1)).toBe(true)
    expect(b.sq).toBeLessThan(0.16 * 0.03)
  })

  it('draws an eight-value outline around 50 %', () => {
    const r = physics.outline(1, 2, 9)
    expect(r.split(' / ')).toHaveLength(2)
    for (const v of r.replace(' / ', ' ').split(' ')) {
      expect(parseFloat(v)).toBeGreaterThanOrEqual(41)
      expect(parseFloat(v)).toBeLessThanOrEqual(59)
    }
  })

  it('spawns in the roomiest spot, away from the others and the zones', () => {
    const rand = seeded(3)
    const zone = { left: 0, top: 540, right: 1920, bottom: 1080, margin: 0 }
    const others = [body({ x: 300, y: 200, r: 200 })]
    const at = physics.findSpawn(others, world([zone]), 120, rand, 60)
    expect(at.y).toBeLessThan(540 - 100)
    expect(Math.hypot(at.x - 300, at.y - 200)).toBeGreaterThan(320)
  })
})

describe('jelly standby timeline', () => {
  const games = ['a', 'b', 'c', 'd'].map(k => ({ key: k }))

  it('deals every game once before any twice, skipping those on screen', () => {
    const deck = director.createDeck(games, seeded())
    const dealt = [0, 1, 2, 3].map(() => deck.next().key)
    expect(new Set(dealt).size).toBe(4)
    const onScreen = new Set(['a', 'b', 'c'])
    expect(deck.next(onScreen).key).toBe('d')
  })

  it('never deals a dropped game, and returns null when nothing is left', () => {
    const deck = director.createDeck(games, seeded())
    deck.drop('a'); deck.drop('b')
    for (let i = 0; i < 8; i++) expect(['c', 'd']).toContain(deck.next().key)
    expect(deck.next(new Set(['c', 'd']))).toBeNull()
  })

  it('deals games added later before the rest, once each', () => {
    const deck = director.createDeck(games.slice(0, 2), seeded())
    deck.next()
    deck.add([{ key: 'a' }, { key: 'x' }, { key: 'y' }])
    expect(new Set([deck.next().key, deck.next().key])).toEqual(new Set(['x', 'y']))
  })

  it('builds the feature reel: clips first, then screenshots, as games', () => {
    const item = (f: string, url = `/m/${f}`) => ({ system_id: 'gba', filename: f, display_name: f.toUpperCase(),
      system_name: 'Game Boy Advance', last_played: null, url })
    const reel = director.featureReel({ videos: [item('v1'), item('bad', '')], stills: [item('s1')] })
    expect(reel.map((r: Mod) => [r.kind, r.game.key])).toEqual([['video', 'gba:v1'], ['still', 'gba:s1']])
    expect(reel[0].game).toMatchObject({ title: 'V1', systemName: 'Game Boy Advance', filename: 'v1' })
    expect(director.featureReel(null)).toEqual([])
  })

  it('caps a clip at 20 s and gives a still its pan', () => {
    expect(director.showSeconds('video', 14)).toBe(14)
    expect(director.showSeconds('video', 95)).toBe(director.CLIP_MAX_S)
    expect(director.showSeconds('video', NaN)).toBe(director.CLIP_MAX_S)
    expect(director.showSeconds('still', 14)).toBe(director.STILL_S)
  })

  /** Every action the director starts over `seconds`, with its time. */
  const timeline = (d: Mod, seconds: number, onShow?: (t: number) => void) => {
    const out: [number, string][] = []
    for (let t = 0; t <= seconds; t = Math.round((t + 0.1) * 10) / 10) {
      for (const a of d.tick(t)) { out.push([t, a]); if (a === 'show') onShow?.(t) }
    }
    return out
  }

  it('features a game every ~25 s: gather, show, release, settle', () => {
    const d = director.createDirector(seeded())
    const steps = timeline(d, 80, () => d.showFor(10)).filter(([, a]) => a !== 'pop')
    expect(steps.map(([, a]) => a).slice(0, 5)).toEqual(['gather', 'show', 'release', 'settle', 'gather'])
    const at = Object.fromEntries(steps.slice(0, 5).map(([t, a], i) => [`${a}${i}`, t]))
    expect(at.gather0).toBe(director.FIRST_FEATURE_S)
    expect(at.show1 - at.gather0).toBeCloseTo(director.GATHER_S, 0)
    expect(at.release2 - at.show1).toBeCloseTo(10, 0)
    expect(at.gather4 - at.settle3).toBeCloseTo(director.FEATURE_GAP_S, 0)
  })

  it('a clip that ends early releases at once; one that never says stops at 20 s', () => {
    const d = director.createDirector(seeded())
    let shown = -1
    const early = timeline(d, 30, (t) => { shown = t })
    expect(early.find(([, a]) => a === 'release')![0] - shown).toBeCloseTo(director.CLIP_MAX_S, 0)
    const e = director.createDirector(seeded())
    for (let t = 0; t < 10; t += 0.1) e.tick(t)
    e.endShow(10)
    expect(e.tick(10.1)).toContain('release')
  })

  it('pops now and then, never while a jelly grows or shrinks', () => {
    const d = director.createDirector(seeded())
    const steps = timeline(d, 120, () => d.showFor(10))
    const pops = steps.filter(([, a]) => a === 'pop').map(([t]) => t)
    expect(pops[0]).toBe(director.FIRST_POP_S)
    expect(pops.length).toBeGreaterThanOrEqual(6)
    for (let i = 1; i < pops.length; i++) expect(pops[i] - pops[i - 1]).toBeGreaterThanOrEqual(director.POP_GAP_S[0] - 0.01)
    const busy = steps.filter(([, a]) => a === 'gather' || a === 'release').map(([t]) => t)
    for (const p of pops) for (const b of busy) expect(p >= b && p < b + 1.6).toBe(false)
  })
})
