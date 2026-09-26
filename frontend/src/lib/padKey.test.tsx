/**
 * Hints are drawn as controller buttons, never as keyboard keys.
 */
import { render } from '@testing-library/react'
import { createElement } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { PadHints, PadKey } from './padKey'
import { buildSdk } from './themeSdk'

describe('pad prompts', () => {
  it('turns a hint string into buttons and keeps the labels', () => {
    const { container } = render(createElement(PadHints,
      { text: '↑↓ Navigate · ✕ Select · ○ Back · L1/R1 Page' }))
    const text = container.textContent || ''
    expect(text).toContain('Navigate')
    expect(text).toContain('Page')
    expect(text).not.toMatch(/[↑↓←→]/)                 // no arrow "keys" left
    expect(container.querySelectorAll('svg')).toHaveLength(3)   // d-pad, ✕, ○
    expect(container.querySelector('[data-k="L1 R1"]')?.textContent).toBe('L1R1')
    expect(container.querySelector('kbd')).toBeNull()
  })

  it('draws compound labels piece by piece', () => {
    const { container } = render(createElement(PadKey, { k: 'D-Pad / L-stick' }))
    expect(container.querySelectorAll('svg')).toHaveLength(1)
    expect(container.textContent).toContain('L-stick')
  })

  it('draws the host’s global buttons as buttons, not as words', () => {
    // ≡ opens game options and PS ×2 the session menu; both are advertised
    // in hint strings, so their names must be read as keys.
    const { container } = render(createElement(PadHints,
      { text: 'Options Game options · PS ×2 Sessions' }))
    expect(container.querySelector('[data-k="Options"]')?.textContent).toBe('Options')
    expect(container.querySelector('[data-k="PS ×2"]')?.textContent).toBe('PS×2')
    expect(container.textContent).toContain('Game options')
    expect(container.textContent).toContain('Sessions')
  })

  it('reaches themes through the SDK', () => {
    const sdk = buildSdk('orbit', { selectTheme: async () => {} } as never)
    expect(sdk.ui.PadKey).toBe(PadKey)
    expect(sdk.ui.PadHints).toBe(PadHints)
  })
})

describe('the host’s global buttons', () => {
  const sdk = buildSdk('shelf', { selectTheme: async () => {} } as never)
  const onGp = sdk.input.onGp as (e: string, h: () => void) => () => void

  it.each(['gp:guide', 'gp:menu', 'gp:power'])('cannot be bound by a theme: %s', (event) => {
    // A theme handler on these ran a second action on the same press.
    let ran = false
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const off = onGp(event, () => { ran = true })
    window.dispatchEvent(new CustomEvent(event))
    off()
    expect(ran).toBe(false)
    expect(warn).toHaveBeenCalled()
    expect(sdk.input.events).not.toContain(event)
    warn.mockRestore()
  })

  it('leaves the triggers to the theme', () => {
    let flips = 0
    const off = onGp('gp:l2', () => { flips++ })
    window.dispatchEvent(new CustomEvent('gp:l2'))
    off()
    expect(flips).toBe(1)
  })
})
