/**
 * The universal pad diagram: the standard layout by POSITION, no brand shape
 * and no face symbols, so every mapped pad is drawn correctly by construction.
 *
 * Colours are CSS variables with the built-in UI's values as fallbacks; a
 * theme repaints it from its stylesheet (`--pd-body`, `--pd-part`, `--pd-line`,
 * `--pd-lit`, `--pd-lit-line`, `--pd-knob`, `--pd-label`, `--pd-callout`,
 * `--pd-callout-ink`, and `--pd-pos` for the legend's position icon).
 * Controls the pad does not have are drawn dashed.
 */
import type { ReactNode } from 'react'

export interface PadDiagramProps {
  /** Held controls by name: south, east, l1, up, home, l3… */
  pressed: Record<string, boolean>
  /** Analog travel 0..1 for l2 / r2. */
  triggers: { l2: number; r2: number }
  /** [leftX, leftY, rightX, rightY], each -1..1. */
  axes: number[]
  /** Controls this pad has; the rest are drawn absent. */
  has: ReadonlySet<string>
  /** Triggers are buttons: draw them like L1/R1, with no travel. */
  digitalTriggers?: boolean
  /** Letter every part, instruction-manual style, instead of naming it. */
  callouts?: boolean
}

const v = (name: string, fallback: string) => `var(--pd-${name}, ${fallback})`
const C = {
  body: v('body', '#15151d'), bodyLine: v('body-line', 'rgba(255,255,255,0.08)'),
  part: v('part', '#23232d'), line: v('line', 'rgba(255,255,255,0.3)'),
  lit: v('lit', '#f2a46a'), litLine: v('lit-line', '#f8cfa9'),
  knob: v('knob', '#3a3a47'), label: v('label', 'rgba(255,255,255,0.78)'),
  callout: v('callout', '#17161A'), calloutInk: v('callout-ink', '#fff'),
}
const TRAVEL = 26
const LETTERS = 'ABCDEFGHIJK'
// Callout letter positions, one per part: L2 L1 R2 R1 d-pad face sticks×2 Select Start Home.
const CALLOUTS: [number, number][] = [[80, 33], [80, 75], [560, 33], [560, 75], [128, 122],
  [562, 122], [212, 318], [428, 318], [262, 116], [378, 116], [352, 186]]

function partStyle(present: boolean, on: boolean) {
  if (!present) return { fill: 'none', stroke: C.line, strokeDasharray: '5 6', opacity: 0.7 }
  return { fill: on ? C.lit : C.part, stroke: on ? C.litLine : C.line }
}

function Label({ x, y, anchor, children, small, absent }: {
  x: number; y: number; anchor: 'start' | 'middle' | 'end'; children: ReactNode; small?: boolean; absent?: boolean
}) {
  return <text x={x} y={y} textAnchor={anchor} className="gc-pd-label"
    style={{ fill: C.label, fontSize: small ? 17 : 20, fontWeight: 600, opacity: absent ? 0.55 : 1 }}>{children}</text>
}

export default function PadDiagram({ pressed, triggers, axes, has, digitalTriggers = false, callouts = false }: PadDiagramProps) {
  const text = !callouts
  const is = (k: string) => !!pressed[k]

  const bumper = (x: number, y: number, k: string, label: string, side: 'l' | 'r') => (
    <g key={k}>
      <rect x={x} y={y} width={150} height={26} rx={8} strokeWidth={2} style={partStyle(has.has(k), is(k))} />
      {text && <Label x={side === 'l' ? x - 14 : x + 164} y={y + 19} anchor={side === 'l' ? 'end' : 'start'} absent={!has.has(k)}>{label}</Label>}
    </g>
  )

  const trigger = (x: number, k: 'l2' | 'r2', label: string, side: 'l' | 'r') => {
    if (digitalTriggers) return bumper(x, 20, k, label, side)
    const value = Math.max(0, Math.min(1, triggers[k]))
    const w = Math.round(142 * value)
    // Fills from the inner edge, the way the trigger travels towards the pad.
    const fx = side === 'l' ? x + 146 - w : x + 4
    const pct = value > 0.02 && value < 0.98 ? ` ${Math.round(value * 100)}%` : ''
    return (
      <g key={k}>
        <rect x={x} y={18} width={150} height={30} rx={15} strokeWidth={2} style={partStyle(has.has(k), false)} />
        {has.has(k) && w > 0 && <rect x={fx} y={22} width={w} height={22} rx={11} style={{ fill: C.lit }} />}
        {text && <Label x={side === 'l' ? x - 14 : x + 164} y={39} anchor={side === 'l' ? 'end' : 'start'} absent={!has.has(k)}>{label}{pct}</Label>}
      </g>
    )
  }

  const arm = (k: string, x: number, y: number, w: number, h: number) =>
    <rect key={k} x={x} y={y} width={w} height={h} rx={6} strokeWidth={2} style={partStyle(has.has(k), is(k))} />

  const dot = (k: string, x: number, y: number) =>
    <circle key={k} cx={x} cy={y} r={19} strokeWidth={2} style={partStyle(has.has(k), is(k))} />

  const stick = (cx: number, k: 'ls' | 'rs', click: string, ax: number, ay: number) => {
    const moved = Math.hypot(ax, ay) > 0.15
    return (
      <g key={k}>
        <circle cx={cx} cy={262} r={40} strokeWidth={2} style={partStyle(has.has(k), false)} />
        {has.has(k) && <circle cx={cx + ax * TRAVEL} cy={262 + ay * TRAVEL} r={23}
          strokeWidth={moved ? 3 : 2}
          style={{ fill: is(click) ? C.lit : C.knob, stroke: moved ? C.litLine : C.line }} />}
      </g>
    )
  }

  const pill = (k: string, x: number, label: string) => (
    <g key={k}>
      <rect x={x - 22} y={138} width={44} height={18} rx={9} strokeWidth={2} style={partStyle(has.has(k), is(k))} />
      {text && <Label x={x} y={182} anchor="middle" small absent={!has.has(k)}>{label}</Label>}
    </g>
  )

  const [lx = 0, ly = 0, rx = 0, ry = 0] = axes
  return (
    <svg className="gc-pd" viewBox="-40 0 720 340" aria-hidden="true" style={{ width: '100%', height: 'auto', display: 'block', overflow: 'visible' }}>
      <path strokeWidth={2} style={{ fill: C.body, stroke: C.bodyLine }}
        d="M150 104 H490 C590 104 640 170 640 236 C640 300 600 330 560 330 C520 330 500 300 470 280 H170 C140 300 120 330 80 330 C40 330 0 300 0 236 C0 170 50 104 150 104 Z" />
      {trigger(110, 'l2', 'L2', 'l')}{bumper(110, 62, 'l1', 'L1', 'l')}
      {trigger(380, 'r2', 'R2', 'r')}{bumper(380, 62, 'r1', 'R1', 'r')}
      {arm('up', 117, 149, 22, 30)}{arm('down', 117, 201, 22, 30)}
      {arm('left', 76, 179, 30, 22)}{arm('right', 139, 179, 30, 22)}
      <rect x={117} y={179} width={22} height={22} style={{ fill: C.part }} />
      {dot('north', 512, 150)}{dot('east', 552, 190)}{dot('south', 512, 230)}{dot('west', 472, 190)}
      {stick(212, 'ls', 'l3', lx, ly)}{stick(428, 'rs', 'r3', rx, ry)}
      {pill('select', 262, 'Select')}{pill('start', 378, 'Start')}
      <g>
        <circle cx={320} cy={214} r={17} strokeWidth={2} style={partStyle(has.has('home'), is('home'))} />
        {text && <Label x={320} y={258} anchor="middle" small absent={!has.has('home')}>Home</Label>}
      </g>
      {callouts && CALLOUTS.map(([x, y], i) => (
        <g key={i}>
          <circle cx={x} cy={y} r={12} style={{ fill: C.callout }} />
          <text x={x} y={y + 5} textAnchor="middle" style={{ fill: C.calloutInk, fontSize: 15, fontWeight: 700 }}>{LETTERS[i]}</text>
        </g>
      ))}
    </svg>
  )
}

// Its own variable: a legend icon must reach 3:1 where the diagram's light may not.
const POS = `var(--pd-pos, ${C.lit})`

/** The legend's position icon: the four face dots, one of them filled. */
export function PadPosition({ pos, size = 34 }: { pos: 'north' | 'east' | 'south' | 'west'; size?: number }) {
  const at = { north: [13, 5], east: [21, 13], south: [13, 21], west: [5, 13] } as const
  return (
    <svg className="gc-pd-pos" width={size} height={size} viewBox="0 0 26 26" aria-hidden="true" style={{ verticalAlign: 'middle', flex: 'none' }}>
      {(Object.keys(at) as (keyof typeof at)[]).map(k => (
        <circle key={k} cx={at[k][0]} cy={at[k][1]} r={k === pos ? 5.5 : 3.5} strokeWidth={1.6}
          style={{ fill: k === pos ? POS : 'none', stroke: k === pos ? POS : 'currentColor' }} />
      ))}
    </svg>
  )
}
