import {hiss, tone} from './synth.js'

/** Shelf's five UI sounds: cardboard, wood and plastic, things on a real shelf.
 * Taps are filtered noise over a low thud; the notes are a small marimba. */

/** A wooden bar: the fundamental and the bright fourth partial a marimba has. */
const bar = (ctx, out, freq, at, peak) => {
  tone(ctx, out, {freq, at, dur: 0.22, peak})
  tone(ctx, out, {freq: freq * 3.9, at, dur: 0.05, peak: peak * 0.25})
}

export const SOUNDS = {
  // A fingertip on a cardboard box.
  move: (ctx, out) => {
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
}
