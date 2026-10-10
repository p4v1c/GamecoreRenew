import {hiss, tone} from './synth.js'

/** Summer's five UI sounds: drops, a steel drum, a wave, a beach in the
 * afternoon. Quieter than the surf behind them, never over it. */

/** A steel-drum note: a round fundamental with the octave and twelfth over it. */
const pan = (ctx, out, freq, at, peak) => {
  tone(ctx, out, {freq, at, dur: 0.38, peak})
  tone(ctx, out, {freq: freq * 2, at, dur: 0.22, peak: peak * 0.3})
  tone(ctx, out, {freq: freq * 3, at, dur: 0.12, peak: peak * 0.18})
}

export const SOUNDS = {
  // A water drop.
  move: (ctx, out) => tone(ctx, out, {freq: 700, to: 1500, dur: 0.05, peak: 0.05}),
  // Two pan notes, a sixth apart.
  confirm: (ctx, out) => { pan(ctx, out, 587.33, 0, 0.06); pan(ctx, out, 880, 0.08, 0.06) },
  // A drop falling back, one low pan note.
  back: (ctx, out) => {
    tone(ctx, out, {freq: 1300, to: 600, dur: 0.07, peak: 0.045})
    pan(ctx, out, 440, 0.05, 0.05)
  },
  // A wave coming in, and the pan rolling up with it.
  launch: (ctx, out) => {
    hiss(ctx, out, {freq: 400, to: 1800, filter: 'lowpass', q: 0.6, dur: 0.9, peak: 0.04, attack: 0.35})
    ;[523.25, 659.25, 783.99, 1046.5].forEach((freq, i) => pan(ctx, out, freq, 0.12 + i * 0.09, 0.05))
  },
  // The boot, timed on views/splash.js: a wave rolling in as the sun climbs,
  // a slow warm swell rising with it, and when the sun clears the horizon
  // (1.7 s) a steel-drum chord, then the wave drawing back.
  boot: (ctx, out) => {
    hiss(ctx, out, {freq: 250, to: 1100, filter: 'lowpass', q: 0.5, dur: 1.9, peak: 0.035, attack: 1.1})
    tone(ctx, out, {freq: 196, to: 261.63, type: 'triangle', dur: 1.8, peak: 0.025, attack: 0.9})
    ;[392, 493.88, 587.33, 783.99].forEach((freq, i) => pan(ctx, out, freq, 1.7 + i * 0.11, 0.05))
    hiss(ctx, out, {freq: 1100, to: 300, filter: 'lowpass', q: 0.5, at: 2.2, dur: 1.6, peak: 0.022, attack: 0.3})
  },
  // The sea, then a soft chord over it.
  startup: (ctx, out) => {
    hiss(ctx, out, {freq: 300, to: 900, filter: 'lowpass', q: 0.5, dur: 1.4, peak: 0.03, attack: 0.6})
    ;[392, 493.88, 587.33].forEach((freq, i) => pan(ctx, out, freq, 0.5 + i * 0.1, 0.04))
  },
}
