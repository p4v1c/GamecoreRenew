/**
 * The sea, heard.
 *
 * Synthesized, like every other sound in GameCore — no audio file to ship, no
 * fetch latency at boot, no loop seam to hide. Filtered noise is what surf
 * actually is; two slow LFOs on the filter and the gain give the swell, and a
 * third, much slower, keeps successive waves from falling into a pattern the
 * ear can lock onto. That last part is what separates ambience from a nuisance
 * over a long session.
 *
 * It follows the ocean it belongs to: brighter and busier at noon, muted and
 * slower at night, and silent whenever the box is asleep or a game is running.
 */
const NOISE_SECONDS = 4

/** Pink-ish noise: white noise is hissy, this reads as water. */
function noiseBuffer(ctx) {
  const len = ctx.sampleRate * NOISE_SECONDS
  const buf = ctx.createBuffer(1, len, ctx.sampleRate)
  const d = buf.getChannelData(0)
  let b0 = 0, b1 = 0, b2 = 0
  for (let i = 0; i < len; i++) {
    const w = Math.random() * 2 - 1
    b0 = 0.997 * b0 + w * 0.0555
    b1 = 0.963 * b1 + w * 0.0750
    b2 = 0.574 * b2 + w * 0.1538
    d[i] = (b0 + b1 + b2 + w * 0.1848) * 0.22
  }
  return buf
}

/**
 * @param ctx   the host's shared AudioContext — never closed, UI sounds live on it
 * @returns     { setLevel, setTod, stop }
 */
export function createAmbience(ctx) {
  const out = ctx.createGain()
  out.gain.value = 0
  out.connect(ctx.destination)

  const src = ctx.createBufferSource()
  src.buffer = noiseBuffer(ctx)
  src.loop = true

  // The surf itself: a lowpass that opens and closes with each wave.
  const surf = ctx.createBiquadFilter()
  surf.type = 'lowpass'
  surf.frequency.value = 520
  surf.Q.value = 0.6

  // Rolls off the rumble that a TV's speakers turn to mud.
  const rumble = ctx.createBiquadFilter()
  rumble.type = 'highpass'
  rumble.frequency.value = 110

  const swell = ctx.createGain()
  swell.gain.value = 0.5

  src.connect(rumble).connect(surf).connect(swell).connect(out)

  // Two waves at incommensurable periods, plus a slow drift: the pattern never
  // repeats audibly, which is the whole point of an ambience.
  const lfo = (period, depth, target, base) => {
    const osc = ctx.createOscillator()
    osc.type = 'sine'
    osc.frequency.value = 1 / period
    const amp = ctx.createGain()
    amp.gain.value = depth
    osc.connect(amp).connect(target)
    target.value = base
    osc.start()
    return osc
  }

  const oscs = [
    lfo(9.3, 0.26, swell.gain, 0.46),    // the wave you hear
    lfo(23.7, 0.12, swell.gain, 0.46),   // the one under it
    lfo(11.6, 260, surf.frequency, 560), // spray as the wave breaks
  ]

  src.start()

  let level = 0
  const ramp = (v, secs = 1.2) => {
    const t = ctx.currentTime
    out.gain.cancelScheduledValues(t)
    out.gain.setValueAtTime(out.gain.value, t)
    out.gain.linearRampToValueAtTime(v, t + secs)
  }

  return {
    /** 0 silences it; the caller folds in the player's volume setting. */
    setLevel(v) { level = Math.max(0, Math.min(1, v)); ramp(level * 0.09) },
    /** Follows the solar clock: night is quieter and duller than noon. */
    setTod(tod) {
      const t = ctx.currentTime
      const bright = tod === 'day' ? 1 : tod === 'night' ? 0.55 : 0.78
      surf.frequency.cancelScheduledValues(t)
      surf.frequency.setTargetAtTime(560 * bright, t, 6)
    },
    stop() {
      ramp(0, 0.6)
      setTimeout(() => {
        try { oscs.forEach(o => o.stop()); src.stop(); out.disconnect() } catch {}
      }, 800)
    },
  }
}
