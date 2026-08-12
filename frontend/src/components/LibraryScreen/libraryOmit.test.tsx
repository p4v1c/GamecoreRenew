/**
 * Two handlers on one button, and the mechanism that ends it.
 *
 * The host opens the per-game overlay picker on R2 — "because every face
 * button is already spoken for on this screen". Shelf's library binds R2 to
 * cycle how the shelf is stacked and prints `R2  <mode>` in its own hint bar.
 * Both were live at once, so one press turned the box AND opened a menu that
 * no theme surface advertised; the next press turned the box behind it.
 *
 * The host cannot detect that on its own — `onGp` has no notion of a claimed
 * event — so the theme declares it, the same way `powerOmit` already works for
 * the power menu.
 */
import { render } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const listeners: Record<string, Array<() => void>> = {}
vi.mock('../../hooks/useGamepad', async (orig) => {
  const real = await orig<Record<string, unknown>>()
  return {
    ...real,
    onGp: (ev: string, fn: () => void) => {
      ;(listeners[ev] ??= []).push(fn)
      return () => { listeners[ev] = (listeners[ev] ?? []).filter(f => f !== fn) }
    },
  }
})

import LibraryScreen from './index'

beforeEach(() => {
  for (const k of Object.keys(listeners)) delete listeners[k]
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200, statusText: 'OK', json: async () => [],
  })))
})
afterEach(() => { vi.unstubAllGlobals() })

const boundR2 = () => (listeners['gp:r2'] ?? []).length

describe('the library’s R2 shortcut', () => {
  it('is bound when no theme has claimed it', () => {
    // The built-in UI draws its own library and advertises nothing on R2, so
    // the picker keeps its route there.
    render(<LibraryScreen />)
    expect(boundR2()).toBe(1)
  })

  it('is dropped when the theme says it binds R2 itself', () => {
    render(<LibraryScreen omit={['options']} />)
    expect(boundR2()).toBe(0)
  })

  it('is dropped rather than merely guarded', () => {
    // Deferring instead of dropping would leave both handlers registered, and
    // both would still run — which is the bug, not a fix for it.
    render(<LibraryScreen omit={['options']} />)
    expect(listeners['gp:r2']).toSatisfy((l: unknown) => l === undefined || (l as []).length === 0)
  })

  it('ignores an id it does not know', () => {
    // A theme naming something that is not a shortcut must not silently take
    // one away.
    render(<LibraryScreen omit={['not-a-shortcut']} />)
    expect(boundR2()).toBe(1)
  })
})
