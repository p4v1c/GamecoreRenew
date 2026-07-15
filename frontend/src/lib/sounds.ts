/**
 * UI sounds — synthesized with WebAudio (no audio assets, no fetch latency).
 *
 * playSound('move' | 'confirm' | 'back' | 'launch' | 'startup')
 *
 * Enabled state and volume persist in localStorage and are editable from
 * Settings → UI Sounds. Sounds are short and quiet by design — a console
 * "tick", not a phone notification.
 */

export type SoundName = 'move' | 'confirm' | 'back' | 'launch' | 'startup'

const LS_ENABLED = 'gc:uiSounds'
const LS_VOLUME = 'gc:uiSoundsVolume'

export const soundSettings = {
  get enabled(): boolean { return localStorage.getItem(LS_ENABLED) !== 'off' },
  set enabled(v: boolean) { localStorage.setItem(LS_ENABLED, v ? 'on' : 'off') },
  get volume(): number {
    const v = parseInt(localStorage.getItem(LS_VOLUME) ?? '60', 10)
    return isNaN(v) ? 60 : Math.max(0, Math.min(100, v))
  },
  set volume(v: number) { localStorage.setItem(LS_VOLUME, String(Math.max(0, Math.min(100, v)))) },
}

let ctx: AudioContext | null = null

function audio(): AudioContext | null {
  if (!ctx) {
    try { ctx = new AudioContext() } catch { return null }
  }
  // Chromium may start the context suspended until a user gesture
  if (ctx.state === 'suspended') ctx.resume().catch(() => {})
  return ctx
}

/** One enveloped oscillator note. */
function note(c: AudioContext, freq: number, at: number, dur: number, peak: number,
              type: OscillatorType = 'sine') {
  const osc = c.createOscillator()
  const gain = c.createGain()
  osc.type = type
  osc.frequency.value = freq
  gain.gain.setValueAtTime(0, at)
  gain.gain.linearRampToValueAtTime(peak, at + 0.008)
  gain.gain.exponentialRampToValueAtTime(0.0001, at + dur)
  osc.connect(gain).connect(c.destination)
  osc.start(at)
  osc.stop(at + dur + 0.05)
}

export function playSound(name: SoundName) {
  if (!soundSettings.enabled) return
  const c = audio()
  if (!c) return
  const v = soundSettings.volume / 100
  const t = c.currentTime

  switch (name) {
    case 'move':
      note(c, 880, t, 0.05, 0.06 * v, 'sine')
      break
    case 'confirm':
      note(c, 523.25, t, 0.07, 0.10 * v, 'triangle')          // C5
      note(c, 659.25, t + 0.06, 0.10, 0.10 * v, 'triangle')   // E5
      break
    case 'back':
      note(c, 440, t, 0.06, 0.08 * v, 'triangle')             // A4
      note(c, 349.23, t + 0.05, 0.09, 0.08 * v, 'triangle')   // F4
      break
    case 'launch':
      // Rising arpeggio — the "here we go" chime
      note(c, 523.25, t, 0.12, 0.11 * v, 'triangle')
      note(c, 659.25, t + 0.09, 0.12, 0.11 * v, 'triangle')
      note(c, 783.99, t + 0.18, 0.14, 0.11 * v, 'triangle')
      note(c, 1046.5, t + 0.27, 0.30, 0.10 * v, 'sine')
      break
    case 'startup':
      // Soft C major swell
      note(c, 261.63, t, 1.1, 0.05 * v, 'sine')
      note(c, 329.63, t + 0.12, 1.0, 0.05 * v, 'sine')
      note(c, 392.0, t + 0.24, 0.9, 0.05 * v, 'sine')
      note(c, 523.25, t + 0.36, 0.9, 0.04 * v, 'sine')
      break
  }
}

/** Sound for a gamepad UI event name, or null for silent events. */
export function soundForGpEvent(event: string): SoundName | null {
  switch (event) {
    case 'gp:dpad-up':
    case 'gp:dpad-down':
    case 'gp:dpad-left':
    case 'gp:dpad-right':
    case 'gp:l1':
    case 'gp:r1':
    case 'gp:l2':
    case 'gp:r2':
      return 'move'
    case 'gp:confirm':
    case 'gp:menu':
    case 'gp:power':
      return 'confirm'
    case 'gp:back':
      return 'back'
    default:
      return null
  }
}
