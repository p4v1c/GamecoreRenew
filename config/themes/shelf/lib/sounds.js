import {hiss, tone} from './synth.js'

/** Shelf's UI sounds: cardboard, wood and plastic, things on a real shelf.
 * Taps are filtered noise over a low thud; the notes are a small marimba.
 *
 * The library has its own three, because there the d-pad does not move a
 * cursor, it handles a box: `swap` (one box back in the row, the next one out),
 * `flip` / `unflip` (L2 turns it over and back) and `restack` (R2). They are
 * played by lib/browse.js; the bus still fires `move` for those presses, so
 * `move` stays quiet while the library has the pad, or every press would be a
 * tap on top of a slide. */

/** A wooden bar: the fundamental and the bright fourth partial a marimba has. */
const bar = (ctx, out, freq, at, peak) => {
  tone(ctx, out, {freq, at, dur: 0.22, peak})
  tone(ctx, out, {freq: freq * 3.9, at, dur: 0.05, peak: peak * 0.25})
}

/** ±4 %, so twenty boxes in a row do not sound like one sample twenty times. */
const vary = () => 0.96 + Math.random() * 0.08

/** Closer than this to the last swap and the d-pad is being tapped through the
 *  shelf: the box only grazes its neighbours, so the sound is shorter too. */
const BURST_MS = 140
let lastSwap = -Infinity

export const createSounds = (sdk) => {
  // The same gate lib/browse.js uses before it handles a press.
  const libraryHasPad = () => {
    const s = sdk.nav.get()
    return s.screen === 'library' && !s.modalDepth && s.sessionGameKey == null
  }

  return {
    // A fingertip on a cardboard box.
    move: (ctx, out) => {
      if (libraryHasPad()) return
      hiss(ctx, out, {freq: 1800, q: 2.5, dur: 0.03, peak: 0.05})
      tone(ctx, out, {freq: 190, to: 120, dur: 0.05, peak: 0.05})
    },
    // Two wooden notes, up.
    confirm: (ctx, out) => { bar(ctx, out, 784, 0, 0.09); bar(ctx, out, 1046.5, 0.07, 0.09) },
    // Two wooden notes, down.
    back: (ctx, out) => { bar(ctx, out, 659.25, 0, 0.08); bar(ctx, out, 523.25, 0.07, 0.08) },
    // The cartridge: a slide, a clunk, a click, then the shelf answers.
    launch: (ctx, out) => {
      hiss(ctx, out, {freq: 1100, to: 500, q: 1.5, dur: 0.18, peak: 0.035, attack: 0.05})
      tone(ctx, out, {freq: 150, to: 85, at: 0.18, dur: 0.14, peak: 0.12})
      hiss(ctx, out, {freq: 4200, filter: 'highpass', at: 0.19, dur: 0.025, peak: 0.05})
      bar(ctx, out, 784, 0.36, 0.07)
      bar(ctx, out, 1174.66, 0.44, 0.07)
    },
    // G B D G on the marimba.
    startup: (ctx, out) => [392, 493.88, 587.33, 783.99].forEach((freq, i) => bar(ctx, out, freq, i * 0.12, 0.06)),

    // A box drawn out of the row: cardboard sliding on cardboard, then it
    // settles in the hand with a soft knock and the grain of the edge.
    swap: (ctx, out) => {
      const now = performance.now()
      const burst = now - lastSwap < BURST_MS
      lastSwap = now
      const v = vary()
      if (burst) {
        hiss(ctx, out, {freq: 900 * v, to: 1500 * v, q: 1.4, dur: 0.05, peak: 0.03, attack: 0.01})
        tone(ctx, out, {freq: 150 * v, to: 110 * v, at: 0.04, dur: 0.04, peak: 0.045})
        return
      }
      hiss(ctx, out, {freq: 700 * v, to: 1600 * v, q: 1.2, dur: 0.12, peak: 0.05, attack: 0.03})
      tone(ctx, out, {freq: 140 * v, to: 95 * v, at: 0.1, dur: 0.07, peak: 0.075})
      hiss(ctx, out, {freq: 3500, filter: 'highpass', at: 0.1, dur: 0.02, peak: 0.018})
    },
    // Turning the box over: the air it moves, rising, then the flap of the
    // card landing on its back.
    flip: (ctx, out) => {
      const v = vary()
      hiss(ctx, out, {freq: 400 * v, to: 1800 * v, filter: 'lowpass', dur: 0.16, peak: 0.03, attack: 0.06})
      hiss(ctx, out, {freq: 2600, filter: 'highpass', at: 0.15, dur: 0.03, peak: 0.04})
      tone(ctx, out, {freq: 230 * v, to: 160 * v, at: 0.15, dur: 0.05, peak: 0.05})
    },
    // And back to the front: the same gesture, the air falling.
    unflip: (ctx, out) => {
      const v = vary()
      hiss(ctx, out, {freq: 1800 * v, to: 400 * v, filter: 'lowpass', dur: 0.16, peak: 0.03, attack: 0.04})
      hiss(ctx, out, {freq: 2600, filter: 'highpass', at: 0.15, dur: 0.03, peak: 0.035})
      tone(ctx, out, {freq: 200 * v, to: 140 * v, at: 0.15, dur: 0.05, peak: 0.05})
    },
    // Restacking the shelf: three boxes knocked square against the wood.
    restack: (ctx, out) => [180, 160, 205].forEach((freq, i) => {
      const v = vary()
      tone(ctx, out, {freq: freq * v, to: freq * 0.7 * v, at: i * 0.06, dur: 0.05, peak: 0.06})
      hiss(ctx, out, {freq: 2200 * v, q: 2, at: i * 0.06, dur: 0.02, peak: 0.02})
    }),
  }
}
