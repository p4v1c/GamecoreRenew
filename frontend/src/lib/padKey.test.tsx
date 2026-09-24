/**
 * Hints are drawn as controller buttons, never as keyboard keys.
 */
import { render } from '@testing-library/react'
import { createElement } from 'react'
import { describe, expect, it } from 'vitest'
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

  it('reaches themes through the SDK', () => {
    const sdk = buildSdk('orbit', { selectTheme: async () => {} } as never)
    expect(sdk.ui.PadKey).toBe(PadKey)
    expect(sdk.ui.PadHints).toBe(PadHints)
  })
})
