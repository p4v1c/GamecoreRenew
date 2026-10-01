import {tone} from './synth.js'

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
  // C E G C, each note bouncing in.
  startup: (ctx, out) => [523.25, 659.25, 783.99, 1046.5].forEach((freq, i) =>
    tone(ctx, out, {freq, type: 'triangle', at: i * 0.11, dur: 0.32, peak: 0.06, wobble: WOBBLE})),
}
