/**
 * Haptics.
 *
 * Two things are worth pinning here, and neither is "does it vibrate".
 *
 * The first is that it does **nothing** unless somebody asked. The box has
 * never vibrated; shipping a default table would change how the console feels
 * on every press of every button, on every box, as a side effect of a theme
 * feature nobody had opted into.
 *
 * The second is the ceiling. A pattern is data a downloaded theme wrote, it
 * runs on hardware the player is holding, and unlike a broken grid it cannot be
 * seen on screen to be diagnosed — a pad buzzing for a minute is just a pad
 * that seems broken.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearThemeRumble, rumble, rumbleForGpEvent, rumbleSettings, setThemeRumble,
} from './rumble'

/** A pad whose actuator records what it was asked to do. */
function padWithActuator() {
  const effects: Record<string, number>[] = []
  const pad = {
    vibrationActuator: {
      playEffect: (_type: string, params: Record<string, number>) => {
        effects.push(params)
        return Promise.resolve('complete')
      },
    },
  }
  vi.stubGlobal('navigator', { getGamepads: () => [pad] })
  return effects
}

beforeEach(() => {
  localStorage.clear()
  clearThemeRumble()
  vi.unstubAllGlobals()
})

describe('nothing vibrates unless a theme asked for it', () => {
  it('has no pattern for any event out of the box', () => {
    // The host ships an empty table on purpose. This is the assertion that
    // stops someone adding a "nice" default later without deciding to.
    for (const e of ['gp:confirm', 'gp:back', 'gp:dpad-up', 'gp:menu']) {
      expect(rumbleForGpEvent(e)).toBeNull()
    }
  })

  it('answers with the pattern once a theme declares one', () => {
    setThemeRumble({ 'gp:confirm': { duration: 40, strong: 0.4 } })
    expect(rumbleForGpEvent('gp:confirm')).toEqual({ duration: 40, strong: 0.4 })
    expect(rumbleForGpEvent('gp:back')).toBeNull()
  })

  it('forgets the table when the theme goes away', () => {
    setThemeRumble({ 'gp:confirm': { duration: 40 } })
    clearThemeRumble()
    expect(rumbleForGpEvent('gp:confirm')).toBeNull()
  })
})

describe('the player can turn it off', () => {
  it('plays nothing at all when haptics are off', () => {
    const effects = padWithActuator()
    rumbleSettings.enabled = false

    rumble({ duration: 100, strong: 1 })

    expect(effects).toEqual([])
  })

  it('plays when they are on', () => {
    const effects = padWithActuator()
    rumbleSettings.enabled = true

    rumble({ duration: 100, strong: 0.5, weak: 0.25 })

    expect(effects).toHaveLength(1)
    expect(effects[0]).toMatchObject({
      duration: 100, strongMagnitude: 0.5, weakMagnitude: 0.25, startDelay: 0,
    })
  })
})

describe('a pattern is bounded, not trusted', () => {
  beforeEach(() => { rumbleSettings.enabled = true })

  it('caps a single burst', () => {
    const effects = padWithActuator()
    rumble({ duration: 999999, strong: 1 })
    expect(effects[0].duration).toBe(1000)
  })

  it('clamps magnitudes into 0..1', () => {
    const effects = padWithActuator()
    rumble({ duration: 50, strong: 9, weak: -3 })
    expect(effects[0].strongMagnitude).toBe(1)
    expect(effects[0].weakMagnitude).toBe(0)
  })

  it('treats a non-numeric magnitude as no magnitude rather than NaN', () => {
    // NaN reaches playEffect as a magnitude and the whole call is rejected by
    // the browser, so one bad field silently kills a pattern that was
    // otherwise fine.
    const effects = padWithActuator()
    rumble({ duration: 50, strong: 'hard' as unknown as number })
    expect(effects[0].strongMagnitude).toBe(0)
  })

  it('stops a sequence once it has run long enough', () => {
    const effects = padWithActuator()
    rumble(Array.from({ length: 8 }, () => ({ duration: 1000 })))
    // Three seconds of buzzing is already past the point of being feedback.
    const total = effects.reduce((n, e) => n + e.duration, 0)
    expect(total).toBeLessThanOrEqual(3000)
  })

  it('refuses to queue more steps than a pattern should ever have', () => {
    const effects = padWithActuator()
    rumble(Array.from({ length: 40 }, () => ({ duration: 10 })))
    expect(effects.length).toBeLessThanOrEqual(8)
  })

  it('plays a sequence back to back, each step after the last', () => {
    const effects = padWithActuator()
    rumble([{ duration: 50 }, { duration: 30, delay: 20 }])
    expect(effects[0].startDelay).toBe(0)
    // 50 played, then the 20ms gap the theme asked for.
    expect(effects[1].startDelay).toBe(70)
  })
})

describe('no pad, no crash', () => {
  beforeEach(() => { rumbleSettings.enabled = true })

  it('does nothing when no controller is connected', () => {
    vi.stubGlobal('navigator', { getGamepads: () => [] })
    expect(() => rumble({ duration: 50 })).not.toThrow()
  })

  it('does nothing when the pad has no actuator', () => {
    // Most pads expose none through Chromium. Feedback that throws when it is
    // unavailable turns a nicety into a crash on the one screen a player is
    // using to diagnose their controller.
    vi.stubGlobal('navigator', { getGamepads: () => [{ id: 'plain pad' }] })
    expect(() => rumble({ duration: 50 })).not.toThrow()
  })

  it('swallows an actuator that rejects mid-pattern', () => {
    vi.stubGlobal('navigator', {
      getGamepads: () => [{ vibrationActuator: { playEffect: () => Promise.reject(new Error('gone')) } }],
    })
    expect(() => rumble({ duration: 50 })).not.toThrow()
  })
})
