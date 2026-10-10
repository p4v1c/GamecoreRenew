/**
 * Every shipped theme answers the five UI sounds with its own (each adds a
 * `boot` for its splash, and Shelf four for its library), and every one of
 * them stays under the player's volume: it plays into the `out` node the host
 * hands it, never into `ctx.destination`, and every source it starts stops.
 */
import { describe, expect, it } from 'vitest'
import { resolveThemeSounds } from '../lib/themeLoader'

const THEMES = ['jelly', 'orbit', 'shelf', 'summer']
const NAMES = ['move', 'confirm', 'back', 'launch', 'startup']
/** Sounds a theme adds on top of the five, played by the theme itself. */
const EXTRA: Record<string, string[]> = {
  jelly: ['boot'], orbit: ['boot'], summer: ['boot'],
  shelf: ['boot', 'flip', 'restack', 'swap', 'unflip'],
}

/** A theme's sound table: `SOUNDS`, or `createSounds(sdk)` for one that reads state. */
async function soundsOf(theme: string, screen = 'home') {
  const mod = await import(/* @vite-ignore */ `../../../config/themes/${theme}/lib/sounds.js`)
  if (mod.SOUNDS) return mod.SOUNDS
  const sdk = { nav: { get: () => ({ screen, modalDepth: 0, sessionGameKey: null }) } }
  return mod.createSounds(sdk)
}

/** Just enough of an AudioContext to record the graph a sound builds. */
function fakeContext() {
  const edges: Array<[unknown, unknown]> = []
  const sources: Array<{ started: boolean; stopAt: number | null }> = []
  const param = () => ({ value: 0, setValueAtTime() {}, exponentialRampToValueAtTime() {},
    linearRampToValueAtTime() {} })
  const node = (extra: Record<string, unknown> = {}) => {
    const n: Record<string, unknown> = { ...extra }
    n.connect = (to: unknown) => { edges.push([n, to]); return to }
    return n
  }
  const source = (extra: Record<string, unknown>) => {
    const s = { started: false, stopAt: null as number | null }
    sources.push(s)
    return node({ ...extra, start() { s.started = true }, stop(at: number) { s.stopAt = at } })
  }
  const destination = node()
  const ctx = {
    currentTime: 10, sampleRate: 8000, destination,
    createOscillator: () => source({ type: 'sine', frequency: param() }),
    createBufferSource: () => source({ buffer: null }),
    createGain: () => node({ gain: param() }),
    createDelay: () => node({ delayTime: param() }),
    createBiquadFilter: () => node({ type: 'lowpass', frequency: param(), Q: param() }),
    createBuffer: (_c: number, len: number) => ({ getChannelData: () => new Float32Array(len) }),
  }
  return { ctx, edges, sources, destination }
}

describe('theme sounds', () => {
  for (const theme of THEMES) {
    it(`${theme} supplies all five, inside the player's volume`, async () => {
      const resolved = resolveThemeSounds({ id: theme, version: '1' } as never, { sounds: await soundsOf(theme) })
      const names = [...NAMES, ...(EXTRA[theme] ?? [])]
      expect(Object.keys(resolved).sort()).toEqual([...names].sort())
      for (const name of names) {
        const { ctx, edges, sources, destination } = fakeContext()
        const out = { connect() {} }
        ;(resolved[name] as (c: unknown, o: unknown) => void)(ctx, out)
        expect(sources.length, `${theme}.${name} makes no sound`).toBeGreaterThan(0)
        expect(edges.some(([, to]) => to === destination), `${theme}.${name} bypasses the volume`).toBe(false)
        expect(edges.some(([, to]) => to === out), `${theme}.${name} never reaches out`).toBe(true)
        for (const s of sources) {
          expect(s.started).toBe(true)
          expect(s.stopAt).not.toBeNull()
          expect(s.stopAt! - ctx.currentTime).toBeLessThan(5)
        }
      }
    })
  }

  // In the library the d-pad handles boxes and lib/browse.js plays `swap`;
  // the bus's `move` for the same press must not land on top of it.
  it('shelf keeps move quiet while the library has the pad', async () => {
    const sounds = await soundsOf('shelf', 'library')
    const { ctx, sources } = fakeContext()
    sounds.move(ctx, { connect() {} })
    expect(sources.length).toBe(0)
  })
})
