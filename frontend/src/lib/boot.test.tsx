/**
 * The boot gate: three facts, one announcement, and no clock anywhere.
 *
 * What this pins down is the shape of the decision, because the shape is what
 * was wrong. The dashboard used to appear when the boot animation ended, and
 * the animation ended on a timer — four seconds of it added by Electron
 * whenever the machine had booted recently, a duration chosen on one box for
 * every box. On a slow one the home appeared empty and filled in under the
 * player's thumb; on a fast one the box waited for nothing.
 */
import { render, act, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import React from 'react'

import {
  BOOT_STEPS, DEFAULT_BOOT_BACKGROUND, bootBackground, bootSteps, isBootReady,
  markBootStep, onBootChange, resetBootForTests,
} from './boot'

/** Two frames, and enough slack for jsdom to actually run them. */
const frame = () => act(async () => { await new Promise(r => setTimeout(r, 120)) })

beforeEach(() => { resetBootForTests() })
afterEach(() => { cleanup(); vi.restoreAllMocks(); delete (window as { gamecore?: unknown }).gamecore })

describe('what the host waits for', () => {
  it('is not ready until every fact is in', async () => {
    expect(isBootReady()).toBe(false)
    markBootStep('theme')
    expect(isBootReady()).toBe(false)
    markBootStep('systems')
    // `painted` is marked from a frame callback, not from this call.
    expect(isBootReady()).toBe(false)
    await frame()
    expect(isBootReady()).toBe(true)
    expect(bootSteps()).toEqual({ theme: true, systems: true, painted: true })
  })

  it('accepts a successful empty systems response', async () => {
    // A box with no emulator installed has a home that is ready to say so.
    // Waiting for a non-empty list is waiting for the player to have installed
    // something.
    markBootStep('theme')
    markBootStep('systems')
    await frame()
    expect(isBootReady()).toBe(true)
  })

  it('holds nothing back for what a good box can be missing', () => {
    // Not the network, the covers, the scraper, a ROM scan or a connected pad:
    // every one of them is absent on some perfectly good box, and a boot that
    // waits for an optional thing is a boot that hangs on a bad afternoon.
    expect([...BOOT_STEPS]).toEqual(['theme', 'systems', 'painted'])
  })
})

describe('what the shell is told', () => {
  it('is told once, with what was waited for', async () => {
    const bootReady = vi.fn()
    ;(window as unknown as { gamecore: unknown }).gamecore = { bootReady }

    markBootStep('theme')
    markBootStep('systems')
    await frame()

    expect(bootReady).toHaveBeenCalledTimes(1)
    expect(bootReady.mock.calls[0][0].steps).toEqual({ theme: true, systems: true, painted: true })

    markBootStep('theme')          // a second mark changes nothing
    await frame()
    expect(bootReady).toHaveBeenCalledTimes(1)
  })

  it('does not fall over outside Electron', async () => {
    // The browser dev server has nobody to tell, and the interface is ready
    // just the same.
    markBootStep('theme'); markBootStep('systems')
    await frame()
    expect(isBootReady()).toBe(true)
  })
})

describe('who is watching', () => {
  it('re-renders a subscriber when the last fact lands', async () => {
    const Probe = () => {
      const ready = React.useSyncExternalStore(onBootChange, isBootReady)
      return <div data-testid="ready">{String(ready)}</div>
    }
    const r = render(<Probe />)
    expect(r.getByTestId('ready').textContent).toBe('false')

    await act(async () => { markBootStep('theme'); markBootStep('systems') })
    await frame()
    expect(r.getByTestId('ready').textContent).toBe('true')
  })
})

describe('the ground the boot is painted on', () => {
  it('is the one the shell is already painting', () => {
    // The shell read the active theme's declared `boot.background` from disk
    // before this bundle existed. Reading the same value is what keeps the
    // whole boot one colour — Shelf boots to paper, and a dark cover under its
    // splash was a dark-to-white flash at every start.
    ;(window as unknown as { gamecore: unknown }).gamecore = { bootBackground: '#F4F2ED' }
    expect(bootBackground()).toBe('#F4F2ED')
  })

  it('falls back where there is no shell to ask', () => {
    expect(bootBackground()).toBe(DEFAULT_BOOT_BACKGROUND)
    ;(window as unknown as { gamecore: unknown }).gamecore = { bootBackground: null }
    expect(bootBackground()).toBe(DEFAULT_BOOT_BACKGROUND)
  })

  it('refuses anything that is not a colour', () => {
    // It crossed a process boundary and ends up in a style attribute.
    for (const bad of ['red; background:url(http://x)', '', 'transparent', 42, {}]) {
      ;(window as unknown as { gamecore: unknown }).gamecore = { bootBackground: bad }
      expect(bootBackground()).toBe(DEFAULT_BOOT_BACKGROUND)
    }
  })
})
