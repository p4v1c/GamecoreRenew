/** What the standby shows next, and when. Pure: the engine asks on every frame
 * and acts on the answer; the tests drive it with a fake clock. */

/** The first pop comes early so a short visit still sees one. */
export const FIRST_POP_S = 5
/** Between two pops, a random wait in this range. */
export const POP_GAP_S = [10, 16]
export const FIRST_FEATURE_S = 8
/** Swarm time between the end of one feature and the start of the next. */
export const FEATURE_GAP_S = 25
/** The featured jelly comes to the centre and grows, then shrinks back. */
export const GATHER_S = 1.6
export const RELEASE_S = 1.4
/** A clip plays this long at most. */
export const CLIP_MAX_S = 20
/** A screenshot's slow pan, or a lone cover when there is no media at all. */
export const STILL_S = 12

/** Fisher-Yates over a copy, with an injected `rand` in [0, 1). */
export function shuffle(list, rand) {
  const out = [...list]
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

/**
 * The library as a deck: every game comes up once before any comes up twice,
 * so over an evening the jellies show the whole library. A game whose cover
 * fails is `drop`ped and never dealt again.
 */
export function createDeck(games, rand) {
  const byKey = new Map(games.map((g) => [g.key, g]))
  const dropped = new Set()
  let order = shuffle([...byKey.keys()], rand)
  let at = 0

  /** The next game not in `exclude` (keys on screen), or null. */
  function next(exclude = new Set()) {
    const live = [...byKey.keys()].filter((k) => !dropped.has(k) && !exclude.has(k))
    if (!live.length) return null
    for (let n = 0; n < order.length * 2 + 1; n++) {
      if (at >= order.length) { order = shuffle([...byKey.keys()], rand); at = 0 }
      const key = order[at++]
      if (!dropped.has(key) && !exclude.has(key)) return byKey.get(key)
    }
    return byKey.get(live[0])
  }
  return {next, drop: (key) => dropped.add(key), has: (key) => byKey.has(key) && !dropped.has(key)}
}

/** A playlist entry as a standby game: `{key, systemId, filename, ...}`. */
export const gameOfItem = (item) => ({
  key: `${item.system_id}:${item.filename}`, systemId: item.system_id, filename: item.filename,
  title: item.display_name, systemName: item.system_name, lastPlayed: item.last_played || null,
})

/** The feature reel: clips first, then screenshots of the games without one,
 * each with the media it shows. Round robin over the result. */
export function featureReel(playlist) {
  const take = (items, kind) => (Array.isArray(items) ? items : [])
    .filter((it) => it?.url && it.system_id && it.filename)
    .map((it) => ({game: gameOfItem(it), kind, url: it.url}))
  return [...take(playlist?.videos, 'video'), ...take(playlist?.stills, 'still')]
}

/** How long a feature shows: the clip's own length up to CLIP_MAX_S
 * (NaN or Infinity when unknown), a fixed pan for a still or a cover. */
export function showSeconds(kind, duration) {
  if (kind !== 'video') return STILL_S
  if (!Number.isFinite(duration) || duration <= 0) return CLIP_MAX_S
  return Math.min(duration, CLIP_MAX_S)
}

/**
 * The standby's timeline: pops and features. `tick(t)` returns what starts
 * now, in order: 'gather' (a jelly heads for the centre), 'show' (its media
 * plays), 'release' (it shrinks back), 'settle' (it is one of the swarm
 * again), 'pop'. No pop while a jelly is growing or shrinking: two things
 * changing size at once read as noise.
 */
export function createDirector(rand, {gather = GATHER_S, release = RELEASE_S} = {}) {
  let phase = 'swarm'
  let phaseEnd = 0
  let featureAt = FIRST_FEATURE_S
  let popAt = FIRST_POP_S
  let showStart = 0
  const popGap = () => POP_GAP_S[0] + rand() * (POP_GAP_S[1] - POP_GAP_S[0])

  function advance(t) {
    if (phase === 'swarm' && t >= featureAt) { phase = 'gather'; phaseEnd = t + gather; return 'gather' }
    if (phase === 'gather' && t >= phaseEnd) {
      phase = 'show'; showStart = t; phaseEnd = t + CLIP_MAX_S
      return 'show'
    }
    if (phase === 'show' && t >= phaseEnd) { phase = 'release'; phaseEnd = t + release; return 'release' }
    if (phase === 'release' && t >= phaseEnd) { phase = 'swarm'; featureAt = t + FEATURE_GAP_S; return 'settle' }
    return null
  }

  function tick(t) {
    const out = []
    const step = advance(t)
    if (step) out.push(step)
    if (t >= popAt) {
      if (phase === 'gather' || phase === 'release') popAt = phaseEnd + 1
      else { out.push('pop'); popAt = t + popGap() }
    }
    return out
  }

  return {
    tick,
    phase: () => phase,
    /** The shown media's real length is known: end the show after it. */
    showFor(seconds) { if (phase === 'show') phaseEnd = showStart + Math.min(seconds, CLIP_MAX_S) },
    /** The clip ended or failed: release now. */
    endShow(t) { if (phase === 'show') phaseEnd = t },
  }
}
