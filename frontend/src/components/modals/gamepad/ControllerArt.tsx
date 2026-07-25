import { CSSProperties, ReactNode } from 'react'
import { GamepadState, GP_BTN } from '../../../hooks/useGamepad'

/**
 * ControllerArt — the pad drawing of the controller overlay.
 *
 * Ported from the "realistic controller" design mock: a stack of absolutely
 * positioned, shaded layers instead of the flat SVG outline it replaces.
 * Every coordinate below is in the mock's own 372×238 space; the whole thing
 * is scaled as a block, so nothing here needs to know the on-screen size.
 *
 * Purely presentational — it draws whatever GamepadState it is handed.
 */

const ART_W = 372
const ART_H = 238

const ACCENT = '#7c3aed'
const GLOW = '0 0 12px rgba(124,58,237,0.6)'
const ETCH = 'rgba(233,230,242,0.72)'

export type ControllerLayout = 'playstation' | 'xbox' | 'generic'

/** Absolute box positioned by its centre — how the controls are laid out. */
function at(cx: number, cy: number, w: number, h: number): CSSProperties {
  return { position: 'absolute', left: cx - w / 2, top: cy - h / 2, width: w, height: h }
}

// PlayStation pads sit the sticks side by side under the face buttons and put
// the d-pad up top; Xbox pads swap the d-pad and the left stick. Same asymmetry
// the old diagram drew, same two anchor points.
const DPAD_HOME = { x: 78, y: 82 }
const STICK_HOME = { x: 141, y: 139 }
const RSTICK = { x: 231, y: 139 }
const FACE = { x: 285, y: 95 }
const STICK_TRAVEL = 13

const PRESS_TRANSITION = 'transform 90ms ease, box-shadow 90ms ease, filter 90ms ease'

export default function ControllerArt({ layout, state, scale = 1.35 }: {
  layout: ControllerLayout
  state: GamepadState
  scale?: number
}) {
  const held = (btn: number) => state.pressed[btn] ?? false
  /** Trigger travel 0..1 — falls back to the digital state on pads without analog triggers. */
  const pull = (btn: number) => state.values[btn] ?? (held(btn) ? 1 : 0)
  const axis = (i: number) => state.axes[i] ?? 0

  const isXbox = layout === 'xbox'
  const dpad = isXbox ? STICK_HOME : DPAD_HOME
  const lstick = isXbox ? DPAD_HOME : STICK_HOME
  const shoulder = isXbox
    ? { lt: 'LT', rt: 'RT', lb: 'LB', rb: 'RB' }
    : { lt: 'L2', rt: 'R2', lb: 'L1', rb: 'R1' }

  return (
    <div style={{ width: ART_W * scale, height: ART_H * scale, position: 'relative' }}>
      <div style={{ position: 'absolute', left: 0, top: 0, width: ART_W, height: ART_H, transform: `scale(${scale})`, transformOrigin: 'top left' }}>

        {/* Ambient glow under the pad */}
        <div style={{
          ...at(ART_W / 2, ART_H * 0.56, 320, 108), borderRadius: '50%', filter: 'blur(14px)',
          background: 'radial-gradient(50% 50% at 50% 50%, rgba(124,58,237,0.16), rgba(124,58,237,0) 70%)',
        }} />

        {/* Triggers (L2 / R2) — analog: they sink as far as they are pulled */}
        <Trigger cx={87} label={shoulder.lt} tilt={-7} travel={pull(GP_BTN.L2)} />
        <Trigger cx={285} label={shoulder.rt} tilt={7} travel={pull(GP_BTN.R2)} />

        {/* Bumpers (L1 / R1) */}
        <Bumper cx={86} label={shoulder.lb} tilt={-8} pressed={held(GP_BTN.L1)} />
        <Bumper cx={286} label={shoulder.rb} tilt={8} pressed={held(GP_BTN.R1)} />

        {/* Grips */}
        <div style={{
          position: 'absolute', left: 20, top: 92, width: 92, height: 138, transform: 'rotate(-19deg)',
          borderRadius: '44px 28px 46px 40px',
          background: 'linear-gradient(150deg, #43444f 0%, #2c2d38 34%, #191a21 100%)',
          boxShadow: '0 26px 44px -22px rgba(0,0,0,0.95), inset 0 2px 0 rgba(255,255,255,0.07), inset 0 -20px 26px -18px rgba(0,0,0,0.9)',
        }} />
        <div style={{
          position: 'absolute', left: 260, top: 92, width: 92, height: 138, transform: 'rotate(19deg)',
          borderRadius: '28px 44px 40px 46px',
          background: 'linear-gradient(210deg, #43444f 0%, #2c2d38 34%, #191a21 100%)',
          boxShadow: '0 26px 44px -22px rgba(0,0,0,0.95), inset 0 2px 0 rgba(255,255,255,0.07), inset 0 -20px 26px -18px rgba(0,0,0,0.9)',
        }} />

        {/* Body + top gloss */}
        <div style={{
          position: 'absolute', left: 16, top: 42, width: 340, height: 96, borderRadius: '48px 48px 34px 34px',
          background: 'linear-gradient(160deg, #4b4c58 0%, #34353f 26%, #24252e 58%, #171820 100%)',
          boxShadow: '0 30px 60px -26px rgba(0,0,0,0.95), inset 0 2px 0 rgba(255,255,255,0.10), inset 0 -22px 32px -22px rgba(0,0,0,0.85)',
        }} />
        <div style={{
          position: 'absolute', left: 16, top: 42, width: 340, height: 96, borderRadius: '48px 48px 34px 34px',
          background: 'radial-gradient(130% 90% at 26% -20%, rgba(255,255,255,0.15), rgba(255,255,255,0) 55%)',
          pointerEvents: 'none',
        }} />

        {/* Light bar */}
        <div style={{
          ...at(ART_W / 2, 43.5, 78, 7), borderRadius: 4,
          background: 'linear-gradient(180deg, #cfd6ff, #7f8bd8)',
          boxShadow: '0 0 14px rgba(150,170,255,0.45), inset 0 -1px 1px rgba(0,0,0,0.25)',
        }} />

        {/* Touchpad (no standard mapping index — drawn, never lit) */}
        <div style={{
          ...at(ART_W / 2, 71, 104, 42), borderRadius: 7,
          background: 'linear-gradient(180deg, #303140, #1f2028)',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.09), inset 0 0 0 1px rgba(0,0,0,0.45), 0 4px 10px -6px rgba(0,0,0,0.9)',
        }} />

        {/* Share / Options pills */}
        <Pill cx={119} pressed={held(GP_BTN.SHARE)} />
        <Pill cx={253} pressed={held(GP_BTN.OPTIONS)} />

        {/* Guide / PS button */}
        <div style={{
          ...at(ART_W / 2, 106, 16, 16), borderRadius: '50%', transition: PRESS_TRANSITION,
          background: held(GP_BTN.GUIDE)
            ? `radial-gradient(circle at 50% 30%, ${ACCENT}, #2b1b52)`
            : 'radial-gradient(circle at 50% 30%, #2d2e37, #17181e)',
          boxShadow: held(GP_BTN.GUIDE)
            ? `inset 0 1px 0 rgba(255,255,255,0.18), ${GLOW}`
            : 'inset 0 1px 0 rgba(255,255,255,0.10), 0 2px 5px -2px rgba(0,0,0,0.9)',
          transform: held(GP_BTN.GUIDE) ? 'translateY(1.5px)' : 'none',
        }} />

        {/* D-pad */}
        <div style={{
          ...at(dpad.x, dpad.y, 20, 52), borderRadius: 6,
          background: 'linear-gradient(180deg, #34353f, #1d1e25)',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.10), 0 3px 6px -2px rgba(0,0,0,0.8)',
        }} />
        <div style={{
          ...at(dpad.x, dpad.y, 52, 20), borderRadius: 6,
          background: 'linear-gradient(90deg, #313239, #24252d 50%, #313239)',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08), 0 3px 6px -2px rgba(0,0,0,0.8)',
        }} />
        <div style={{
          ...at(dpad.x, dpad.y, 14, 14), borderRadius: '50%',
          background: 'radial-gradient(circle at 50% 35%, #23242c, #14151b)',
          boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.85), inset 0 -1px 0 rgba(255,255,255,0.05)',
        }} />
        <DpadArm cx={dpad.x} cy={dpad.y - 16} w={20} h={22} sink={[0, 1.5]} pressed={held(GP_BTN.DPAD_UP)} />
        <DpadArm cx={dpad.x} cy={dpad.y + 16} w={20} h={22} sink={[0, -1.5]} pressed={held(GP_BTN.DPAD_DOWN)} />
        <DpadArm cx={dpad.x - 18} cy={dpad.y} w={20} h={20} sink={[1.5, 0]} pressed={held(GP_BTN.DPAD_LEFT)} />
        <DpadArm cx={dpad.x + 18} cy={dpad.y} w={20} h={20} sink={[-1.5, 0]} pressed={held(GP_BTN.DPAD_RIGHT)} />

        {/* Face buttons */}
        <FaceButton cx={FACE.x} cy={FACE.y - 26} pressed={held(GP_BTN.Y)}>{glyph('top', isXbox, held(GP_BTN.Y))}</FaceButton>
        <FaceButton cx={FACE.x + 26} cy={FACE.y} pressed={held(GP_BTN.B)}>{glyph('right', isXbox, held(GP_BTN.B))}</FaceButton>
        <FaceButton cx={FACE.x - 26} cy={FACE.y} pressed={held(GP_BTN.X)}>{glyph('left', isXbox, held(GP_BTN.X))}</FaceButton>
        <FaceButton cx={FACE.x} cy={FACE.y + 26} pressed={held(GP_BTN.A)}>{glyph('bottom', isXbox, held(GP_BTN.A))}</FaceButton>

        {/* Sticks — translated by the live axes, sunk when clicked (L3 / R3).
            The socket stays put: without a fixed rim to move against, the cap
            just looks like it is floating. */}
        <Socket cx={lstick.x} cy={lstick.y} />
        <Socket cx={RSTICK.x} cy={RSTICK.y} />
        <Stick cx={lstick.x} cy={lstick.y} dx={axis(0)} dy={axis(1)} pressed={held(GP_BTN.L3)} />
        <Stick cx={RSTICK.x} cy={RSTICK.y} dx={axis(2)} dy={axis(3)} pressed={held(GP_BTN.R3)} />
      </div>
    </div>
  )
}

// ── Parts ─────────────────────────────────────────────────────────────────────

function Label({ text, pressed }: { text: string; pressed: boolean }) {
  return (
    <span style={{
      fontFamily: 'monospace', fontSize: 9, letterSpacing: '0.14em',
      color: pressed ? '#fff' : 'rgba(233,230,242,0.55)', transition: 'color 90ms ease',
    }}>{text}</span>
  )
}

function Trigger({ cx, label, tilt, travel }: { cx: number; label: string; tilt: number; travel: number }) {
  return (
    <div style={{
      ...at(cx, 15, 82, 26), borderRadius: '15px 15px 4px 4px',
      display: 'flex', justifyContent: 'center', paddingTop: 3,
      background: 'linear-gradient(180deg, #24252f, #14151c)',
      boxShadow: travel > 0
        ? `inset 0 1px 0 rgba(255,255,255,0.06), ${GLOW}`
        : 'inset 0 1px 0 rgba(255,255,255,0.06), 0 6px 12px -6px rgba(0,0,0,0.9)',
      transform: `rotate(${tilt}deg) translateY(${(3 * travel).toFixed(1)}px)`,
      filter: `brightness(${(1 + 0.35 * travel).toFixed(2)})`,
      transition: PRESS_TRANSITION,
    }}>
      <Label text={label} pressed={travel > 0} />
    </div>
  )
}

function Bumper({ cx, label, tilt, pressed }: { cx: number; label: string; tilt: number; pressed: boolean }) {
  return (
    <div style={{
      ...at(cx, 33, 88, 26), borderRadius: '16px 16px 6px 6px',
      display: 'flex', justifyContent: 'center', paddingTop: 4,
      background: 'linear-gradient(180deg, #3b3c48 0%, #272831 55%, #1a1b22 100%)',
      boxShadow: pressed
        ? `inset 0 1px 0 rgba(255,255,255,0.18), ${GLOW}`
        : 'inset 0 1px 0 rgba(255,255,255,0.12), 0 8px 16px -8px rgba(0,0,0,0.9)',
      transform: `rotate(${tilt}deg) translateY(${pressed ? 3 : 0}px)`,
      transition: PRESS_TRANSITION,
    }}>
      <Label text={label} pressed={pressed} />
    </div>
  )
}

function Pill({ cx, pressed }: { cx: number; pressed: boolean }) {
  return (
    <div style={{
      ...at(cx, 57.5, 22, 11), borderRadius: 3,
      background: pressed
        ? `linear-gradient(180deg, ${ACCENT}, #4c2ea0)`
        : 'linear-gradient(180deg, #35363f, #22232b)',
      boxShadow: pressed ? GLOW : 'inset 0 1px 0 rgba(255,255,255,0.08)',
      transform: pressed ? 'translateY(1.5px)' : 'none',
      transition: PRESS_TRANSITION,
    }} />
  )
}

/** The four invisible d-pad arms — they only show up when the direction is held. */
function DpadArm({ cx, cy, w, h, sink, pressed }: {
  cx: number; cy: number; w: number; h: number; sink: [number, number]; pressed: boolean
}) {
  return (
    <div style={{
      ...at(cx, cy, w, h), borderRadius: 6,
      background: pressed ? 'rgba(124,58,237,0.45)' : 'rgba(255,255,255,0)',
      boxShadow: pressed ? `inset 0 1px 3px rgba(0,0,0,0.6), ${GLOW}` : 'none',
      transform: pressed ? `translate(${sink[0]}px, ${sink[1]}px)` : 'none',
      transition: PRESS_TRANSITION,
    }} />
  )
}

function FaceButton({ cx, cy, pressed, children }: {
  cx: number; cy: number; pressed: boolean; children: ReactNode
}) {
  return (
    <div style={{
      ...at(cx, cy, 26, 26), borderRadius: '50%',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: pressed
        ? `radial-gradient(circle at 50% 28%, ${ACCENT}, #331f66 78%)`
        : 'radial-gradient(circle at 50% 28%, #3c3d48, #1d1e25 78%)',
      boxShadow: pressed
        ? `inset 0 2px 4px rgba(0,0,0,0.7), inset 0 0 0 1px rgba(0,0,0,0.5), ${GLOW}`
        : 'inset 0 1px 0 rgba(255,255,255,0.14), inset 0 0 0 1px rgba(0,0,0,0.5), 0 3px 6px -2px rgba(0,0,0,0.85)',
      transform: pressed ? 'translateY(2px)' : 'none',
      transition: PRESS_TRANSITION,
    }}>{children}</div>
  )
}

function Socket({ cx, cy }: { cx: number; cy: number }) {
  return (
    <div style={{
      ...at(cx, cy, 56, 56), borderRadius: '50%',
      background: 'radial-gradient(circle at 50% 40%, #101118, #1c1d25 78%)',
      boxShadow: 'inset 0 3px 6px rgba(0,0,0,0.85), inset 0 -1px 0 rgba(255,255,255,0.05)',
    }} />
  )
}

function Stick({ cx, cy, dx, dy, pressed }: {
  cx: number; cy: number; dx: number; dy: number; pressed: boolean
}) {
  const tx = (dx * STICK_TRAVEL).toFixed(1)
  const ty = (dy * STICK_TRAVEL).toFixed(1)
  return (
    <div style={{
      ...at(cx, cy, 46, 46),
      transform: `translate(${tx}px, ${ty}px) scale(${pressed ? 0.92 : 1})`,
      // No easing on the axes: the stick has to track the thumb, not trail it.
      transition: 'transform 40ms linear, box-shadow 90ms ease',
      borderRadius: '50%',
      boxShadow: pressed ? GLOW : 'none',
    }}>
      <div style={{
        position: 'absolute', inset: 0, borderRadius: '50%',
        background: 'radial-gradient(circle at 50% 25%, #4c4d59, #14151b 72%)',
        boxShadow: 'inset 0 2px 3px rgba(255,255,255,0.10), inset 0 -3px 6px rgba(0,0,0,0.8), 0 6px 12px -6px rgba(0,0,0,0.9)',
      }} />
      <div style={{
        position: 'absolute', left: 7, top: 6, width: 32, height: 32, borderRadius: '50%',
        background: pressed
          ? `radial-gradient(circle at 50% 80%, ${ACCENT}, #1b1130 82%)`
          : 'radial-gradient(circle at 50% 80%, #35363f, #14151a 82%)',
        boxShadow: 'inset 0 -2px 4px rgba(255,255,255,0.07), inset 0 6px 10px rgba(0,0,0,0.9)',
      }} />
    </div>
  )
}

/** Face-button etching: PlayStation shapes, or the Xbox letter for that seat. */
function glyph(seat: 'top' | 'right' | 'bottom' | 'left', isXbox: boolean, pressed: boolean): ReactNode {
  const color = pressed ? '#fff' : ETCH

  if (isXbox) {
    const letter = { top: 'Y', right: 'B', bottom: 'A', left: 'X' }[seat]
    return <span style={{ fontSize: 11, fontWeight: 700, lineHeight: 1, color }}>{letter}</span>
  }

  switch (seat) {
    case 'top':
      return <span style={{ width: 0, height: 0, borderLeft: '5.5px solid transparent', borderRight: '5.5px solid transparent', borderBottom: `9.5px solid ${color}` }} />
    case 'right':
      return <span style={{ width: 10, height: 10, border: `1.4px solid ${color}`, borderRadius: '50%' }} />
    case 'left':
      return <span style={{ width: 9, height: 9, border: `1.4px solid ${color}`, borderRadius: 2 }} />
    case 'bottom':
      return <span style={{ fontFamily: 'monospace', fontSize: 12, lineHeight: 1, color }}>✕</span>
  }
}
