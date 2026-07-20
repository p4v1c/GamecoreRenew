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
 * IMPORTANT: When a game session is active, ALL events are suppressed except
 * gp:guide. This mirrors the old C++ behaviour (MainWindow.cpp line 344):
 *   if (m_session.isRunning()) return;  // block everything
 */
import { useEffect, useRef } from 'react'
import { useStore } from '../store'
import { playSound, soundForGpEvent } from '../lib/sounds'

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

function emit(name: string, detail?: unknown) {
  const sound = soundForGpEvent(name)
  if (sound) playSound(sound)
  window.dispatchEvent(new CustomEvent(name, detail !== undefined ? { detail } : undefined))
}

/** True when an emulator / app is running — reads Zustand state synchronously. */
function isPlaying(): boolean {
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

      rafId.current = requestAnimationFrame(poll)
    }

    rafId.current = requestAnimationFrame(poll)
    return () => {
      cancelAnimationFrame(rafId.current)
      window.removeEventListener('gamepadconnected',    onConnect)
      window.removeEventListener('gamepaddisconnected', onDisconnect)
    }
  }, [])
}

/** Attach a gamepad event listener, returns cleanup fn. */
export function onGp(event: string, handler: (detail?: unknown) => void): () => void {
  const listener = (e: Event) => handler((e as CustomEvent).detail)
  window.addEventListener(event, listener)
  return () => window.removeEventListener(event, listener)
}
