/**
 * The live pad diagram: one standard layout, lit by POSITION, with the face
 * symbols the on-screen prompts use.
 *
 * Colours are CSS variables with Orbit-blue fallbacks; a theme repaints it from
 * its stylesheet (`--pd-body`, `--pd-body-line`, `--pd-center`, `--pd-part`,
 * `--pd-line`, `--pd-lit`, `--pd-lit-line`, `--pd-knob`, `--pd-well`, `--pd-label`, and
 * `--pd-pos` for the legend's icon). Controls the pad does not have are faded
 * and dashed.
 */
import { useId } from 'react'

type PadDiagramProps = {
  /** Held controls by name: south, east, l1, up, home, l3… */
  pressed: Record<string, boolean>
  /** Analog travel 0..1 for l2 / r2. */
  triggers: { l2: number; r2: number }
  /** [leftX, leftY, rightX, rightY], each -1..1. */
  axes: number[]
  /** Controls this pad has; the rest are drawn absent. */
  has: ReadonlySet<string>
  /** Triggers are buttons: no travel figure. */
  digitalTriggers?: boolean
}

const v = (name: string, fallback: string) => `var(--pd-${name}, ${fallback})`
const C = {
  body: v('body', '#e0e5ed'), bodyLine: v('body-line', '#fff'), center: v('center', '#171e29'),
  part: v('part', '#202734'), line: v('line', '#616b79'), knob: v('knob', '#333c4a'), well: v('well', '#111923'),
  lit: v('lit', '#63c7ff'), litLine: v('lit-line', '#c0ecff'), label: v('label', '#9aa9bd'),
}
// Ink on a lit part: dark on every theme's light.
const LIT_INK = '#152334'
const STICK_TRAVEL = 13
const ABSENT = 0.25

type Face = 'north' | 'east' | 'south' | 'west'
const FACE_PATHS: Record<Face, string> = {
  north: 'M0 -7 L7 6 L-7 6 Z',
  east: 'M7 0 A7 7 0 1 1 -7 0 A7 7 0 1 1 7 0',
  south: 'M-6 -6 L6 6 M6 -6 L-6 6',
  west: 'M-6 -6 H6 V6 H-6 Z',
}

export default function PadDiagram({ pressed, triggers, axes, has, digitalTriggers = false }: PadDiagramProps) {
  const gradient = useId().replace(/:/g, '')
  const partStyle = (k: string) => ({
    fill: pressed[k] ? C.lit : C.part, stroke: pressed[k] ? C.litLine : C.line,
    opacity: has.has(k) ? 1 : ABSENT, strokeDasharray: has.has(k) ? undefined : '3 4',
  })
  const ink = (k: string) => (pressed[k] ? LIT_INK : C.label)

  const face = (k: Face, x: number, y: number) => (
    <g key={k}>
      <circle cx={x} cy={y} r={15} strokeWidth={1.5} style={partStyle(k)} />
      <path d={FACE_PATHS[k]} transform={`translate(${x} ${y})`} fill="none" stroke={ink(k)} strokeWidth={1.8}
        strokeLinecap="round" strokeLinejoin="round" opacity={has.has(k) ? 1 : ABSENT} />
    </g>
  )

  const stick = (k: 'ls' | 'rs', click: string, x: number, ax = 0, ay = 0) => {
    const kx = x + ax * STICK_TRAVEL
    const ky = 205 + ay * STICK_TRAVEL
    return (
      <g key={k} opacity={has.has(k) ? 1 : ABSENT}>
        <circle cx={x} cy={205} r={31} fill={C.well} stroke={C.line} />
        <circle cx={kx} cy={ky} r={23} strokeWidth={2} fill={pressed[click] ? C.lit : C.knob}
          stroke={Math.hypot(ax, ay) > 0.15 ? C.litLine : C.line} />
        <circle cx={kx} cy={ky} r={18} fill="none" stroke={C.line} opacity={0.4} />
      </g>
    )
  }

  const shoulder = (side: 'l' | 'r', x: number) => {
    const value = triggers[side === 'l' ? 'l2' : 'r2']
    const label = (k: string, y: number, size: number) => (
      <text x={x + 34} y={y} textAnchor="middle" style={{ fill: ink(k), fontSize: size, fontWeight: 700, textShadow: 'none' }}>
        {k.toUpperCase()}
      </text>
    )
    return (
      <g key={side}>
        <rect x={x} y={18} width={68} height={29} rx={10} strokeWidth={1.5} style={partStyle(`${side}2`)} />
        {label(`${side}2`, 38, 16)}
        <rect x={x} y={54} width={68} height={25} rx={8} strokeWidth={1.5} style={partStyle(`${side}1`)} />
        {label(`${side}1`, 72, 15)}
        {!digitalTriggers && value > 0.02 && (
          <text x={side === 'r' ? x + 78 : x - 10} y={38} textAnchor={side === 'r' ? 'start' : 'end'}
            style={{ fill: C.label, fontSize: 12, fontWeight: 600, textShadow: 'none' }}>{Math.round(value * 100)}%</text>
        )}
      </g>
    )
  }

  const [lx, ly, rx, ry] = axes
  return (
    <svg className="gc-pd" viewBox="0 0 500 320" aria-hidden="true" style={{ width: '100%', height: 'auto', display: 'block' }}>
      <defs>
        <linearGradient id={gradient} x2="0" y2="1">
          <stop stopColor={C.body} />
          <stop offset="1" stopColor={C.body} stopOpacity={0.8} />
        </linearGradient>
      </defs>
      {shoulder('l', 80)}{shoulder('r', 352)}
      <path fill={`url(#${gradient})`} stroke={C.bodyLine} strokeWidth={1.5}
        d="M112 83 C76 81 61 115 50 158 L27 257 C19 295 51 310 72 285 L139 226 Q250 251 361 226 L428 285 C449 310 481 295 473 257 L450 158 C439 115 424 81 388 83 Q250 68 112 83Z" />
      <path d="M166 104 Q250 89 334 104 L351 210 Q321 252 250 245 Q179 252 149 210Z" fill={C.center} />
      <path d="M169 104 Q250 89 331 104" fill="none" stroke={C.lit} strokeWidth={3} opacity={0.8} />
      <path d="M177 105 Q250 97 323 105 L316 155 Q250 163 184 155Z" fill={C.part} stroke={C.line} />
      {face('north', 388, 120)}{face('east', 419, 151)}{face('south', 388, 182)}{face('west', 357, 151)}
      {['up', 'right', 'down', 'left'].map((k, i) => (
        <path key={k} d="M103 121 L121 121 L121 138 L112 145 L103 138Z" transform={`rotate(${i * 90} 112 151)`}
          strokeWidth={1.5} style={partStyle(k)} />
      ))}
      {stick('ls', 'l3', 191, lx, ly)}{stick('rs', 'r3', 309, rx, ry)}
      <rect x={148} y={108} width={7} height={18} rx={3} style={partStyle('select')} />
      <rect x={345} y={108} width={7} height={18} rx={3} style={partStyle('start')} />
      <circle cx={250} cy={202} r={9} style={partStyle('home')} />
      {[0, 1, 2, 3, 4].map(i => <circle key={i} cx={238 + i * 6} cy={177} r={1.2} fill={C.line} />)}
    </svg>
  )
}

// Its own variable: a legend icon must reach 3:1 where the diagram's light may not.
const POS = 'var(--pd-pos, #b6dcff)'
const FACE_NAMES: Record<Face, string> = { north: 'Triangle', east: 'Circle', south: 'Cross', west: 'Square' }

/** The legend's icon: the face symbol at that position, as drawn on the diagram. */
export function PadPosition({ pos, size = 34 }: { pos: Face; size?: number }) {
  return (
    <svg className="gc-pd-pos" width={size} height={size} viewBox="-13 -13 26 26" role="img" aria-label={FACE_NAMES[pos]}
      style={{ width: size, height: size, verticalAlign: 'middle', flex: 'none' }}>
      <path d={FACE_PATHS[pos]} fill="none" stroke={POS} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
