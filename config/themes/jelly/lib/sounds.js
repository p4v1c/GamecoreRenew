import {hiss, tone} from './synth.js'

/** Jelly's five UI sounds: bubbles and wobbly boings, a toy box being played
 * with. The host keeps when each one fires; these are what they sound like. */
const WOBBLE = {rate: 16, depth: 22}

export const SOUNDS = {
  // A bubble popping: a short upward chirp.
  move: (ctx, out) => tone(ctx, out, {freq: 520, to: 940, dur: 0.06, peak: 0.07}),
  // Two bouncy plucks that wobble like jelly settling.
  confirm: (ctx, out) => {
    tone(ctx, out, {freq: 660, type: 'triangle', dur: 0.1, peak: 0.09, wobble: WOBBLE})
    tone(ctx, out, {freq: 990, type: 'triangle', at: 0.07, dur: 0.16, peak: 0.09, wobble: WOBBLE})
  },
  // A squish going down.
  back: (ctx, out) => tone(ctx, out, {freq: 720, to: 360, type: 'triangle', dur: 0.12, peak: 0.08,
    wobble: WOBBLE}),
  // A long wobbly slide up, then a pop.
  launch: (ctx, out) => {
    tone(ctx, out, {freq: 330, to: 1320, type: 'triangle', dur: 0.36, peak: 0.08, wobble: {rate: 11, depth: 30}})
    tone(ctx, out, {freq: 1568, to: 2100, at: 0.34, dur: 0.12, peak: 0.08})
  },
  // The boot, timed on views/splash.js and css/moments.css: the mark falls
  // and lands with a boing (0.63 s), each of the eight letters lands with a
  // bubble one step higher, the confetti goes off (1.3 s) and the "Jelly
  // edition" tag pops in (1.5 s).
  boot: (ctx, out) => {
    tone(ctx, out, {freq: 900, to: 260, type: 'triangle', dur: 0.6, peak: 0.04})
    tone(ctx, out, {freq: 196, to: 98, type: 'triangle', at: 0.6, dur: 0.32, peak: 0.12, wobble: {rate: 14, depth: 26}})
    ;[523.25, 587.33, 659.25, 698.46, 783.99, 880, 987.77, 1046.5].forEach((freq, i) =>
      tone(ctx, out, {freq: freq * 0.7, to: freq, at: 0.96 + i * 0.09, dur: 0.09, peak: 0.06}))
    // A party popper: a crack of noise, then sparkles falling.
    hiss(ctx, out, {freq: 3000, filter: 'highpass', at: 1.3, dur: 0.08, peak: 0.07})
    ;[2093, 2637, 3136, 2349, 2794].forEach((freq, i) =>
      tone(ctx, out, {freq, at: 1.36 + i * 0.07, dur: 0.12, peak: 0.022}))
    tone(ctx, out, {freq: 659.25, type: 'triangle', at: 1.55, dur: 0.14, peak: 0.08, wobble: WOBBLE})
    tone(ctx, out, {freq: 987.77, type: 'triangle', at: 1.63, dur: 0.24, peak: 0.08, wobble: WOBBLE})
  },
  // C E G C, each note bouncing in.
  startup: (ctx, out) => [523.25, 659.25, 783.99, 1046.5].forEach((freq, i) =>
    tone(ctx, out, {freq, type: 'triangle', at: i * 0.11, dur: 0.32, peak: 0.06, wobble: WOBBLE})),
}
