/**
 * One layout, three surfaces — the seam, tested where it can actually break.
 *
 * The settings screen and the power menu used to live under
 * `config/themes/_shared/` and be imported by relative path from each theme.
 * They are host code now, handed to themes through `sdk.defaults`, and drawn by
 * the built-in UI directly.
 *
 * That move has exactly two failure modes, and both are silent:
 *
 *   1. The factories stop being on `sdk.defaults`. Every theme's settings
 *      screen and power menu vanish at once, and nothing else notices — the
 *      themes destructure them at build time and would throw at first render.
 *   2. The built-in screen renders, but the palette does not reach it. The
 *      colours live on `.gcs-skin-default`, a class the host passes in; drop it
 *      and the screen comes out with a theme's colours or with none.
 */
import { render, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { buildSdk } from '../lib/themeSdk'
import * as defaults from '../components/defaults'
import SettingsScreen from '../components/modals/SettingsScreen'

const sdk = () => buildSdk('shelf', { selectTheme: vi.fn(async () => {}) })

beforeEach(() => {
  // Every endpoint answers `{}` — a 200 with the wrong shape, which is what a
  // proxy, a validation error or a half-started service actually sends. This
  // is not a convenience stub: the pages here store list answers and map over
  // them, and before `asList` this exact response killed the screen with
  // "nets.map is not a function" before it drew a row. On the fallback UI there
  // is nothing behind that.
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200, statusText: 'OK', json: async () => ({}),
  })))
})

describe('the seam themes reach the shared screens through', () => {
  it('puts both factories on sdk.defaults', () => {
    // Shelf and Summer both open with `const { createSettings, createPowerView }
    // = sdk.defaults`. If these ever stop being exported, every theme's
    // settings screen and power menu break together.
    const s = sdk()
    expect(typeof (s.defaults as Record<string, unknown>).createSettings).toBe('function')
    expect(typeof (s.defaults as Record<string, unknown>).createPowerView).toBe('function')
  })

  it('is the same code the host renders, not a copy of it', () => {
    const s = sdk()
    expect((s.defaults as Record<string, unknown>).createSettings).toBe(defaults.createSettings)
    expect((s.defaults as Record<string, unknown>).createPowerView).toBe(defaults.createPowerView)
  })

  it('gives a surface no extra class when it asks for no skin', () => {
    // A theme passes no skin: its own stylesheet colours the screen from
    // `:root`, and an unasked-for class here could outrank it.
    const Screen = defaults.createSettings(sdk(), {}, {}) as React.ComponentType<{ onClose: () => void }>
    const { container } = render(<Screen onClose={() => {}} />)
    expect(container.querySelector('.gcs-set')?.className).toBe('gcs-set')
  })
})

describe('the built-in settings screen', () => {
  it('draws the rail, not the old list of ten rows', async () => {
    const { container } = render(<SettingsScreen onClose={() => {}} />)
    // Scoped to the rail on purpose: "Wi-Fi" is also the heading of the page
    // beside it, and a query over the whole screen would match either and
    // prove neither.
    const rail = () => container.querySelector('.gcs-set-rail')
    await waitFor(() => expect(rail()).toBeTruthy())
    const rows = [...rail()!.querySelectorAll('.gcs-set-row')].map(r => r.textContent ?? '')
    // The capture's nine, in its order. The list this replaced had Storage,
    // Standby and Update as top-level rows; the rail folds them into System,
    // which is the difference that matters.
    for (const label of ['Wi-Fi', 'Bluetooth', 'Display', 'Audio', 'Controllers',
                         'Emulators & apps', 'BIOS', 'Themes', 'System']) {
      expect(rows.some(r => r.includes(label)), `${label} is missing from the rail`).toBe(true)
    }
    expect(rows).toHaveLength(9)
  })

  it('carries the class its palette is scoped to', () => {
    // Without this the screen renders in whatever colours happen to be loaded —
    // including a theme's, when safe mode swaps just this surface back.
    const { container } = render(<SettingsScreen onClose={() => {}} />)
    expect(container.querySelector('.gcs-set.gcs-skin-default')).toBeTruthy()
  })

  it('opens even when nothing on the box answers', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('no box') }))
    const { container } = render(<SettingsScreen onClose={() => {}} />)
    // Same rule as the list it replaced: a settings screen that fails to open
    // because a service is down is the last thing this surface may do.
    await waitFor(() =>
      expect(container.querySelectorAll('.gcs-set-rail .gcs-set-row')).toHaveLength(9))
  })
})
