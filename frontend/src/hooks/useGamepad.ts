/**
 * useGamepad — Browser Gamepad API hook.
 *
 * Polls at 60fps. Emits CustomEvents so any component can listen without
 * prop-drilling. Supports PS4, Xbox, and generic XInput controllers.
 *
 * Events dispatched on window:
 *   gp:dpad-up | gp:dpad-down | gp:dpad-left | gp:dpad-right
 *   gp:confirm (A/Cross)  | gp:back (B/Circle)  | gp:y (Y/Triangle) | gp:x (X/Square)
 *   gp:menu (Start/Options) | gp:power (Share/Back) | gp:guide (PS/Home)
 *   gp:l1 | gp:r1 | gp:l2 | gp:r2
 *   gp:connected(name) | gp:disconnected
 *
 * Those events are edge-triggered ("□ was pressed"). Anything that needs the
 * continuous picture instead ("□ is held", "the left stick sits at 40%") —
 * i.e. the controller overlay — reads it through useGamepadState() below.
 *
 * IMPORTANT: When a game session is active, ALL events are suppressed except
 * gp:guide. This mirrors the old C++ behaviour (MainWindow.cpp line 344):
 *   if (m_session.isRunning()) return;  // block everything
 */
import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store'
import { playSound, soundForGpEvent } from '../lib/sounds'
import { api } from '../api'
import { rumble, rumbleForGpEvent } from '../lib/rumble'

const DEAD_ZONE = 0.5

// Guide/PS button must be pressed twice within this window to emit gp:guide
// (single press ignored — avoids accidentally killing the running game).
const GUIDE_DOUBLE_PRESS_MS = 1000

// Standard mapping indices (matches browser standard gamepad mapping)
const BTN = {
  A: 0, B: 1, X: 2, Y: 3,
  L1: 4, R1: 5, L2: 6, R2: 7,
  SHARE: 8, OPTIONS: 9,
  L3: 10, R3: 11,
  DPAD_UP: 12, DPAD_DOWN: 13, DPAD_LEFT: 14, DPAD_RIGHT: 15,
  GUIDE: 16,
} as const

/** Per-frame subscribers (see useGamepadState) — fed by the poll loop below. */
type FrameListener = (gp: Gamepad | null) => void
const frameListeners = new Set<FrameListener>()

/**
 * How long a press is allowed to mean "wake up" and nothing else.
 *
 * The guard below swallows input until the backend says the box is awake. If
 * that word never comes — websocket down, backend wedged — the pad would stop
 * working with no screen left to explain why, which is worse than anything the
 * guard prevents. So the swallow is bounded: ask, wait this long, then let go
 * whatever happened.
 */
export const WAKE_GRACE_MS = 4000

/** Events that are news about the pad, not something the player did with it. */
const NOT_INPUT = new Set(['gp:connected', 'gp:disconnected'])

let wakePending = false
let wakeTimer: ReturnType<typeof setTimeout> | null = null

function clearWake() {
  if (wakeTimer) clearTimeout(wakeTimer)
  wakeTimer = null
  wakePending = false
}

/**
 * Ask the box to wake, once per sleep, however hard the player mashes.
 *
 * The backend wakes on evdev already — but evdev is exactly what a box whose
 * account is outside the `input` group does not have, and gamepad_monitor says
 * so itself: a refused device is "invisible everywhere". Chromium still sees
 * the pad, so the frontend asks too. Two routes to the same idempotent call.
 */
function askToWake() {
  if (wakePending) return
  wakePending = true
  api.standby.exit().catch(() => {})
  wakeTimer = setTimeout(() => {
    wakeTimer = null
    wakePending = false
    if (useStore.getState().standby !== 'off') useStore.getState().setStandby('off')
  }, WAKE_GRACE_MS)
}

// The flag follows the truth rather than being cleared by hand: the box waking
// is what ends the wake, and that arrives over the websocket, not through here.
useStore.subscribe((s, prev) => {
  if (s.standby === 'off' && prev.standby !== 'off') clearWake()
})

function emit(name: string, detail?: unknown) {
  // Asleep, the first press is a wake and only a wake.
  //
  // The standby overlay is a picture — it covers the screen and stops nothing
  // — and in `sleep` there is not even a picture, because the panel is off
  // through DPMS. Without this the cursor moved, menus opened and ✕ launched a
  // game onto a television that was switched off. See standbyInput.test.ts.
  //
  // Here rather than in the overlay, because a theme draws its own standby
  // screen and a guard living in the picture is lost with the picture.
  //
  // Two things are not guarded. A pad arriving or leaving, because those are
  // not presses — a Bluetooth pad that re-pairs by itself in the night would
  // otherwise wake the box every time it flapped. And anything at all while a
  // game is running: the backend wakes the box on launch, but if those two ever
  // disagree this guard would swallow gp:guide, which is the only way to end a
  // game. A stuck flag must never cost the player the button that gets them
  // out. The session rule below takes over there, unchanged.
  if (!NOT_INPUT.has(name) && !isPlaying() && useStore.getState().standby !== 'off') {
    askToWake()
    return
  }
  const sound = soundForGpEvent(name)
  if (sound) playSound(sound)
  // Both feedback channels fire from here, from the same decision, so a theme
  // that dresses one and not the other cannot desynchronise them. Empty unless
  // a theme filled the table in — nothing on this box vibrated before.
  const pattern = rumbleForGpEvent(name)
  if (pattern) rumble(pattern)
  window.dispatchEvent(new CustomEvent(name, detail !== undefined ? { detail } : undefined))
}

/** True when an emulator / app is running — reads Zustand state synchronously.
 *
 * Exported because `onGamepadFrame` subscribers have to apply it themselves:
 * the frame callback is deliberately outside the guard below, and anything that
 * *acts* on a frame rather than just displaying it needs this. One name for the
 * invariant, so there is no second definition to drift. */
export function isPlaying(): boolean {
  return useStore.getState().sessionGameKey !== null
}

export function useGamepad() {
  const prevButtons = useRef<boolean[]>([])
  const prevAxes = useRef<number[]>([])
  const rafId = useRef<number>(0)
  const lastGuidePress = useRef<number>(0)

  useEffect(() => {
    const onConnect    = (e: GamepadEvent) => emit('gp:connected', e.gamepad.id)
    const onDisconnect = () => emit('gp:disconnected')
    window.addEventListener('gamepadconnected',    onConnect)
    window.addEventListener('gamepaddisconnected', onDisconnect)

    function poll() {
      const gamepads = navigator.getGamepads()
      const gp = gamepads.find(g => g !== null)

      if (gp) {
        const playing = isPlaying()

        // Buttons
        gp.buttons.forEach((btn, i) => {
          const pressed = btn.pressed
          const wasPressed = prevButtons.current[i] ?? false

          if (pressed && !wasPressed) {
            // Asleep, every button is the same button: the one that wakes the
            // box. Checked here as well as in emit() because the two branches
            // below leave without going through it — the guide's first press
            // is only remembered, so a single PS on a sleeping box would have
            // asked for nothing at all. Never while a game runs, for the reason
            // emit() gives.
            if (!playing && useStore.getState().standby !== 'off') {
              askToWake()
              prevButtons.current[i] = pressed
              return
            }

            // Guide/PS button always passes through — used to kill the emulator.
            // The browser may or may not expose it (Chromium often blocks it);
            // the backend evdev monitor is the primary path for this button.
            // Requires a double press within GUIDE_DOUBLE_PRESS_MS.
            if (i === BTN.GUIDE) {
              const now = performance.now()
              if (now - lastGuidePress.current <= GUIDE_DOUBLE_PRESS_MS) {
                lastGuidePress.current = 0
                emit('gp:guide')
              } else {
                lastGuidePress.current = now
              }
              prevButtons.current[i] = pressed
              return
            }

            // All other buttons are blocked while a game is running.
            // This prevents emulator inputs from accidentally triggering
            // GameCore UI actions (power menu, launching another game, etc.).
            if (playing) {
              prevButtons.current[i] = pressed
              return
            }

            switch (i) {
              case BTN.DPAD_UP:    emit('gp:dpad-up');    break
              case BTN.DPAD_DOWN:  emit('gp:dpad-down');  break
              case BTN.DPAD_LEFT:  emit('gp:dpad-left');  break
              case BTN.DPAD_RIGHT: emit('gp:dpad-right'); break
              case BTN.A:          emit('gp:confirm');    break
              case BTN.B:          emit('gp:back');       break
              case BTN.Y:          emit('gp:y');          break
              case BTN.X:          emit('gp:x');          break
              case BTN.OPTIONS:    emit('gp:menu');       break
              case BTN.SHARE:      emit('gp:power');      break
              case BTN.L1:         emit('gp:l1');         break
              case BTN.R1:         emit('gp:r1');         break
              case BTN.L2:         emit('gp:l2');         break
              case BTN.R2:         emit('gp:r2');         break
            }
          }
          prevButtons.current[i] = pressed
        })

        // Left stick → d-pad equivalent (edge-triggered). Also blocked during gameplay.
        if (!playing) {
          const ax = gp.axes[0] ?? 0
          const ay = gp.axes[1] ?? 0
          const prevAx = prevAxes.current[0] ?? 0
          const prevAy = prevAxes.current[1] ?? 0

          if (ax > DEAD_ZONE && prevAx <= DEAD_ZONE)   emit('gp:dpad-right')
          if (ax < -DEAD_ZONE && prevAx >= -DEAD_ZONE) emit('gp:dpad-left')
          if (ay > DEAD_ZONE && prevAy <= DEAD_ZONE)   emit('gp:dpad-down')
          if (ay < -DEAD_ZONE && prevAy >= -DEAD_ZONE) emit('gp:dpad-up')

          prevAxes.current[0] = ax
          prevAxes.current[1] = ay
        }
      }

      // Raw snapshot, deliberately outside the `playing` guard above: the
      // controller screen has to keep mirroring the pad, and a held combo is not
      // edge-triggered so it cannot come through the events above.
      //
      // That means a subscriber which *acts* on a frame must call isPlaying()
      // itself. This comment used to assert no subscriber ever did — and the
      // L1+R1 theme rescue in useTheme did, which is how the box reset its own
      // theme mid-game.
      if (frameListeners.size) frameListeners.forEach(cb => cb(gp ?? null))

      rafId.current = requestAnimationFrame(poll)
    }

    rafId.current = requestAnimationFrame(poll)

    // Keyboard stand-in. The box is controller-only, but a browser on a desk is
    // how anyone develops, reviews a theme or rescues a machine over VNC — and
    // until now nothing but Enter on an already-focused tile worked there.
    // These emit the *same* gp:* events, so the default UI and every theme get
    // it for free and nobody writes a second navigation path.
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      // Never steal a keystroke from a real field (Wi-Fi password, search box).
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const name = KEYMAP[e.key]
      if (!name) return
      if (isPlaying() && name !== 'gp:guide') return
      e.preventDefault()
      emit(name)
    }
    window.addEventListener('keydown', onKey)

    return () => {
      cancelAnimationFrame(rafId.current)
      window.removeEventListener('gamepadconnected',    onConnect)
      window.removeEventListener('gamepaddisconnected', onDisconnect)
      window.removeEventListener('keydown', onKey)
    }
  }, [])
}

/**
 * Keyboard → the same events the pad emits.
 * Letters mirror the stand-in the design mockups use, so a theme reviewed in a
 * browser behaves like the box.
 */
const KEYMAP: Record<string, string> = {
  ArrowUp: 'gp:dpad-up', ArrowDown: 'gp:dpad-down',
  ArrowLeft: 'gp:dpad-left', ArrowRight: 'gp:dpad-right',
  Enter: 'gp:confirm', ' ': 'gp:confirm',
  Escape: 'gp:back', Backspace: 'gp:back',
  PageUp: 'gp:l1', PageDown: 'gp:r1',
  m: 'gp:menu', M: 'gp:menu',      // Start  → Settings
  p: 'gp:power', P: 'gp:power',    // Select → Power menu
  c: 'gp:x', C: 'gp:x',            // Square → Controller screen
}

/** Attach a gamepad event listener, returns cleanup fn. */
export function onGp(event: string, handler: (detail?: unknown) => void): () => void {
  const listener = (e: Event) => handler((e as CustomEvent).detail)
  window.addEventListener(event, listener)
  return () => window.removeEventListener(event, listener)
}

// ── Continuous state ──────────────────────────────────────────────────────────

/** Standard-mapping button indices, for consumers of GamepadState.pressed. */
export const GP_BTN = BTN

export interface GamepadState {
  connected: boolean
  /** Held state, indexed by GP_BTN. */
  pressed: boolean[]
  /** Analog travel 0..1, indexed by GP_BTN — only the triggers report in-between. */
  values: number[]
  /** [leftX, leftY, rightX, rightY], each -1..1. */
  axes: number[]
}

const IDLE_STATE: GamepadState = { connected: false, pressed: [], values: [], axes: [0, 0, 0, 0] }

/** Quantise to 1/50th so a resting stick's jitter doesn't re-render every frame. */
const quantise = (v: number) => Math.round(v * 50) / 50

/** Subscribe to the raw per-frame snapshot. Returns cleanup fn. */
export function onGamepadFrame(cb: FrameListener): () => void {
  frameListeners.add(cb)
  return () => { frameListeners.delete(cb) }
}

/**
 * Live button/axis state of the active pad, for views that draw it.
 * Re-renders only when something actually moved (see quantise).
 */
export function useGamepadState(): GamepadState {
  const [state, setState] = useState<GamepadState>(IDLE_STATE)
  const signature = useRef('')

  useEffect(() => onGamepadFrame(gp => {
    const next: GamepadState = gp ? {
      connected: true,
      pressed: gp.buttons.map(b => b.pressed),
      values: gp.buttons.map(b => quantise(b.value)),
      axes: [0, 1, 2, 3].map(i => quantise(gp.axes[i] ?? 0)),
    } : IDLE_STATE

    const sig = JSON.stringify(next)
    if (sig === signature.current) return
    signature.current = sig
    setState(next)
  }), [])

  return state
}
