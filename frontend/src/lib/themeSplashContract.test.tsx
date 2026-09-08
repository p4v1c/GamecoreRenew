/**
 * The SDK 4 boot contract, checked against both shipped themes.
 *
 * A boot animation has a duration; a box being usable does not. The two used
 * to be the same event: the splash ended, the dashboard appeared, and whether
 * there was anything on it was a matter of luck and machine speed. The
 * contract splits them — the animation ends on a held frame, and the host says
 * when it may leave.
 *
 * Both directions are asserted, and the second is the one that keeps old
 * themes alive: a splash that waited for a prop an older host never passes
 * would be a box that never boots.
 */
import { render, act, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import React, { createElement } from 'react'
import { buildSdk } from './themeSdk'

const THEMES = ['shelf', 'summer', 'orbit'] as const

/** Longer than either theme's whole timeline (shelf ~2.7s, summer ~6s). */
const WHOLE_ANIMATION_MS = 12000

const run = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })

/**
 * Run the whole animation, several times over.
 *
 * Each phase of these splashes arms the next one from a state update, so a
 * single advance only reaches the timers that existed when it started. Three
 * passes cover the longest chain (summer: rise → held → out) with room over.
 */
const settleAnimation = async () => {
  for (let i = 0; i < 3; i++) await run(WHOLE_ANIMATION_MS)
}

async function splashOf(theme: string) {
  const sdk = buildSdk(theme, { selectTheme: vi.fn(async () => {}) })
  const mod = await import(/* @vite-ignore */ `../../../config/themes/${theme}/views/splash.js`)
  return mod.createSplash(sdk)
}

afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks() })

describe.each(THEMES)('%s — the splash and the host', (theme) => {
  it('holds its last frame while the interface is not ready', async () => {
    vi.useFakeTimers()
    const Splash = await splashOf(theme)
    const onDone = vi.fn()
    render(createElement(Splash, { onDone, bootReady: false }))

    await settleAnimation()
    expect(onDone).not.toHaveBeenCalled()
  })

  it('leaves when the host says the interface is ready', async () => {
    vi.useFakeTimers()
    const Splash = await splashOf(theme)
    const onDone = vi.fn()
    const r = render(createElement(Splash, { onDone, bootReady: false }))

    await settleAnimation()
    r.rerender(createElement(Splash, { onDone, bootReady: true }))
    await settleAnimation()
    expect(onDone).toHaveBeenCalledTimes(1)
  })

  it('still ends on a host that knows nothing about the contract', async () => {
    // An older front end passes no prop at all. `bootReady !== false` is what
    // makes that the old behaviour rather than a box stuck on its title card.
    vi.useFakeTimers()
    const Splash = await splashOf(theme)
    const onDone = vi.fn()
    render(createElement(Splash, { onDone }))

    await settleAnimation()
    expect(onDone).toHaveBeenCalledTimes(1)
  })
})
