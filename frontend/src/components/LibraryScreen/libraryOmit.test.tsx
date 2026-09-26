/**
 * What a theme may take from the library, and what it may not.
 *
 * `libraryOmit` drops the host's own handler for a shortcut the theme binds
 * itself. It used to accept 'options' (R2): Shelf took it for its restack, and
 * the per-game overlay picker then had no route on Shelf at all. The picker is
 * on ≡ now, owned by the shell, and no id reaches it.
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

const bound = (ev: string) => (listeners[ev] ?? []).length

describe('the library’s shortcuts', () => {
  it('leaves both triggers to the theme', () => {
    // L2 and R2 are theme territory: Shelf flips and restacks with them.
    render(<LibraryScreen />)
    expect(bound('gp:l2')).toBe(0)
    expect(bound('gp:r2')).toBe(0)
  })

  it('does not bind ≡ itself, so the shell decides what one press opens', () => {
    render(<LibraryScreen />)
    expect(bound('gp:menu')).toBe(0)
  })
})
