import {hiss, tone} from './synth.js'

/** Orbit's five UI sounds: glass and air, a cool light in a dark room. Pure
 * sines, open fifths, a short echo for space. */
const SPACE = {time: 0.14, feedback: 0.28}

export const SOUNDS = {
  // A soft glass tick, high and short.
  move: (ctx, out) => {
    tone(ctx, out, {freq: 1760, dur: 0.045, peak: 0.05})
    tone(ctx, out, {freq: 2637, dur: 0.03, peak: 0.018})
  },
  // An open fifth, ringing into the room.
  confirm: (ctx, out) => {
    tone(ctx, out, {freq: 784, dur: 0.22, peak: 0.05, echo: SPACE})
    tone(ctx, out, {freq: 1175, at: 0.05, dur: 0.26, peak: 0.045, echo: SPACE})
  },
  // The same fifth, falling and quieter.
  back: (ctx, out) => {
    tone(ctx, out, {freq: 1175, dur: 0.12, peak: 0.045})
    tone(ctx, out, {freq: 784, at: 0.06, dur: 0.18, peak: 0.045, echo: SPACE})
  },
  // Lift-off: air rushing up, then a chord settling in orbit.
  launch: (ctx, out) => {
    hiss(ctx, out, {freq: 300, to: 4200, filter: 'lowpass', q: 0.7, dur: 0.55, peak: 0.035, attack: 0.25})
    ;[523.25, 783.99, 1046.5].forEach((freq, i) =>
      tone(ctx, out, {freq, at: 0.32 + i * 0.04, dur: 0.8, peak: 0.035, attack: 0.02, echo: SPACE}))
  },
  // The boot, timed on views/splash.js and css/gallery.css: air rising as the
  // rings come in, a glass note as the mark lights (0.5 s), the open fifth
  // under the word (1.1 s), a bright sweep with the line (1.9 s), and the
  // chord settling in orbit under the tagline (2.4 s).
  boot: (ctx, out) => {
    hiss(ctx, out, {freq: 200, to: 2400, filter: 'lowpass', q: 0.6, dur: 2.2, peak: 0.03, attack: 1.2})
    tone(ctx, out, {freq: 98, dur: 3.2, peak: 0.03, attack: 1.0})
    tone(ctx, out, {freq: 1567.98, at: 0.5, dur: 0.6, peak: 0.035, echo: SPACE})
    tone(ctx, out, {freq: 783.99, at: 1.1, dur: 0.9, peak: 0.035, attack: 0.03, echo: SPACE})
    tone(ctx, out, {freq: 1174.66, at: 1.16, dur: 0.9, peak: 0.03, attack: 0.03, echo: SPACE})
    hiss(ctx, out, {freq: 2500, to: 7000, filter: 'bandpass', q: 3, at: 1.9, dur: 0.45, peak: 0.018, attack: 0.15})
    ;[392, 587.33, 783.99, 1174.66].forEach((freq, i) =>
      tone(ctx, out, {freq, at: 2.4 + i * 0.06, dur: 1.8, peak: 0.024, attack: 0.05, echo: SPACE}))
  },
  // A slow detuned swell, like a screen warming up.
  startup: (ctx, out) => [196, 196.6, 293.66, 392].forEach((freq, i) =>
    tone(ctx, out, {freq, at: i * 0.08, dur: 1.6, peak: 0.025, attack: 0.45})),
}
