/** Two building blocks for UI sounds, played into the `out` node the host hands
 * a theme sound: it is already at the player's volume, so nothing here ever
 * touches `ctx.destination`. Copied per theme: a theme folder installs alone. */

/** One enveloped tone. `to` glides the pitch, `wobble` adds a vibrato
 * ({rate} Hz, {depth} Hz), `echo` sends it through a short feedback delay. */
export function tone(ctx, out, {freq, to = freq, type = 'sine', at = 0, dur = 0.08, peak = 0.06,
  attack = 0.005, wobble = null, echo = null}) {
  const t = ctx.currentTime + at
  const osc = ctx.createOscillator()
  const env = ctx.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(freq, t)
  if (to !== freq) osc.frequency.exponentialRampToValueAtTime(to, t + dur)
  if (wobble) {
    const lfo = ctx.createOscillator()
    const depth = ctx.createGain()
    lfo.frequency.value = wobble.rate
    depth.gain.value = wobble.depth
    lfo.connect(depth).connect(osc.frequency)
    lfo.start(t)
    lfo.stop(t + dur + 0.05)
  }
  env.gain.setValueAtTime(0.0001, t)
  env.gain.exponentialRampToValueAtTime(peak, t + attack)
  env.gain.exponentialRampToValueAtTime(0.0001, t + dur)
  osc.connect(env).connect(echo ? delay(ctx, out, echo) : out)
  osc.start(t)
  osc.stop(t + dur + 0.05)
}

/** A burst of filtered noise: a tap, a slide, a wave. `to` sweeps the filter. */
export function hiss(ctx, out, {freq = 2000, to = freq, filter = 'bandpass', q = 1, at = 0,
  dur = 0.05, peak = 0.04, attack = 0.004}) {
  const t = ctx.currentTime + at
  const len = Math.ceil(ctx.sampleRate * (dur + 0.05))
  const buf = ctx.createBuffer(1, len, ctx.sampleRate)
  const data = buf.getChannelData(0)
  for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1
  const src = ctx.createBufferSource()
  const band = ctx.createBiquadFilter()
  const env = ctx.createGain()
  src.buffer = buf
  band.type = filter
  band.Q.value = q
  band.frequency.setValueAtTime(freq, t)
  if (to !== freq) band.frequency.exponentialRampToValueAtTime(to, t + dur)
  env.gain.setValueAtTime(0.0001, t)
  env.gain.exponentialRampToValueAtTime(peak, t + attack)
  env.gain.exponentialRampToValueAtTime(0.0001, t + dur)
  src.connect(band).connect(env).connect(out)
  src.start(t)
  src.stop(t + dur + 0.05)
}

/** A feedback delay into `out`; returns its input. */
function delay(ctx, out, {time = 0.12, feedback = 0.3}) {
  const line = ctx.createDelay(1)
  const loop = ctx.createGain()
  const input = ctx.createGain()
  line.delayTime.value = time
  loop.gain.value = feedback
  input.connect(out)
  input.connect(line).connect(loop).connect(line)
  loop.connect(out)
  return input
}
