/**
 * The two contracts the default UI's look now rests on.
 *
 * Neither is enforced by the type system, and both fail silently: a missing
 * glyph is a hole in a row, and a keyboard that drops its class is a keyboard
 * that quietly goes back to the built-in grey on every theme. Both are the kind
 * of regression you only notice on a television.
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { GLYPHS, Glyph } from './index'
import { VirtualKeyboard } from './VirtualKeyboard'

// The ids SettingsModal draws a row for, in its order.
const ROW_IDS = ['wifi', 'audio', 'bluetooth', 'storage', 'standby',
                 'themes', 'catalog', 'bios', 'update', 'desktop']
// The ids the power menu draws a row for.
const POWER_IDS = ['scan', 'forget', 'shutdown', 'restart', 'desktop']

describe('the icon set', () => {
  it('has a glyph for every row either menu can draw', () => {
    const missing = [...ROW_IDS, ...POWER_IDS].filter(id => !GLYPHS[id])
    expect(missing, 'these rows would render an empty icon tile').toEqual([])
  })

  it('gives shutdown and restart different drawings', () => {
    // They shared one arc once, which put two identical power symbols in a
    // column where one of them turns the box off and the other does not.
    expect(GLYPHS.restart).not.toBe(GLYPHS.shutdown)
  })

  it('renders nothing rather than throwing on a name it does not know', () => {
    // The fallback UI is what a broken theme falls back TO. A missing icon may
    // not be the thing that takes the settings screen down with it.
    const { container } = render(<Glyph name="not-a-real-icon" />)
    expect(container.querySelector('svg')).toBeNull()
  })
})

describe('the on-screen keyboard', () => {
  it('puts its surface name on its own root, where a stylesheet can find it', () => {
    // `--gc-kb-*` are inherited variables, so they have to be set on an
    // ancestor of the keys. If the class lands anywhere but the root — or on
    // nothing at all — the tokens never reach them and every theme's search
    // keyboard goes back to the built-in grey without a single test failing.
    const { container } = render(
      <VirtualKeyboard className="gc-search-kb" onConfirm={() => {}} onCancel={() => {}} />,
    )
    const root = container.firstElementChild as HTMLElement
    expect(root.className).toBe('gc-search-kb')
    expect(root.contains(screen.getByRole('button', { name: 'SPACE' }))).toBe(true)
  })

  it('carries no class when the caller names no surface', () => {
    // The built-in UI passes nothing and must be untouched by all of this.
    const { container } = render(<VirtualKeyboard onConfirm={() => {}} onCancel={() => {}} />)
    expect((container.firstElementChild as HTMLElement).className).toBe('')
  })
})
