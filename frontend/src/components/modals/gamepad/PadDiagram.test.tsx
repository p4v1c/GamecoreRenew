/**
 * The universal diagram: lit by position, absent controls dashed, analog
 * travel shown. The cases are the pads the owner actually plugs in.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import PadDiagram from './PadDiagram'

afterEach(cleanup)

const ALL = new Set(['south', 'east', 'west', 'north', 'l1', 'r1', 'l2', 'r2', 'select', 'start',
  'l3', 'r3', 'up', 'down', 'left', 'right', 'home', 'ls', 'rs'])
const draw = (over: Partial<Parameters<typeof PadDiagram>[0]> = {}) => render(
  <PadDiagram pressed={{}} triggers={{ l2: 0, r2: 0 }} axes={[0, 0, 0, 0]} has={ALL} {...over} />)

const dashed = (c: HTMLElement) => c.querySelectorAll('[style*="stroke-dasharray"]').length
const lit = (c: HTMLElement) => [...c.querySelectorAll('circle, rect')]
  .filter(e => (e as HTMLElement).style.fill.includes('--pd-lit')).length

describe('the pad diagram', () => {
  it('draws a full pad with nothing dashed and nothing lit at rest', () => {
    const { container } = draw()
    expect(dashed(container)).toBe(0)
    expect(lit(container)).toBe(0)
    expect(container.textContent).not.toMatch(/[✕○□△]|\bA\b|\bB\b/)
  })

  it('lights the east dot for a press on the east position, whatever the brand', () => {
    const { container } = draw({ pressed: { east: true } })
    expect(lit(container)).toBe(1)
  })

  it('dashes the sticks an arcade stick does not have', () => {
    const has = new Set([...ALL].filter(c => !['ls', 'rs', 'l3', 'r3'].includes(c)))
    const { container } = draw({ has })
    expect(dashed(container)).toBe(2)
  })

  it('fills an analog trigger and says how far', () => {
    const { container } = draw({ triggers: { l2: 0, r2: 0.6 } })
    expect(container.textContent).toContain('R2 60%')
  })

  it('draws digital triggers as buttons with no travel figure', () => {
    const { container } = draw({ digitalTriggers: true, triggers: { l2: 0, r2: 1 }, pressed: { r2: true } })
    expect(container.textContent).not.toMatch(/%/)
    expect(lit(container)).toBe(1)
  })

  it('letters the parts for a manual page instead of naming them', () => {
    const { container } = draw({ callouts: true })
    expect(container.textContent).toContain('ABCDEFGHIJK')
    expect(container.textContent).not.toContain('L2')
  })

  it('draws every control absent when no pad is connected', () => {
    const { container } = draw({ has: new Set() })
    expect(dashed(container)).toBe(17)   // stick clicks live on the sticks
  })
})
