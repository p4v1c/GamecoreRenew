/**
 * Orbit and Shelf both draw the host's CRT standby (sdk.defaults.CrtStandby),
 * each with its own caption skin, and it goes away with the stage: `sleep` is
 * black with no video element, `off` is nothing at all.
 */
import { createElement } from 'react'
import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { buildSdk } from '../lib/themeSdk'
import { api } from '../api'
import { useStore } from '../store'

const THEMES = '../../../config/themes'
const CLIP = {
  system_id: 'snes9x', filename: 'Chrono Trigger (USA).sfc', display_name: 'Chrono Trigger',
  system_name: 'Super Nintendo', last_played: null, media_type: 'video-normalized',
  url: '/api/media/snes9x/Chrono%20Trigger%20(USA).sfc/media/video-normalized',
}

beforeEach(() => {
  // jsdom has no media pipeline.
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  vi.spyOn(api.standby, 'videos').mockResolvedValue({ videos: [CLIP], stills: [] })
  vi.spyOn(api.standby, 'exit').mockResolvedValue({ ok: true } as never)
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); act(() => useStore.getState().setStandby('off')) })

/** The theme's `screensaver` part, as it hands it to the Shell. */
async function standbyOf(theme: 'orbit' | 'shelf') {
  const sdk = buildSdk(theme, { selectTheme: vi.fn(async () => {}) })
  let parts: Record<string, unknown> = {}
  const defaults = { ...sdk.defaults, Shell: (p: Record<string, unknown>) => { parts = p; return null } }
  const mod = await import(/* @vite-ignore */ `${THEMES}/${theme}/index.js`)
  render(createElement(mod.default({ ...sdk, defaults }).shell))
  cleanup()
  return parts.screensaver as React.ComponentType
}

describe.each([['orbit'], ['shelf']] as const)('%s standby', (theme) => {
  it('is the shared CRT room, in the theme\'s skin, with the game on the caption', async () => {
    const Standby = await standbyOf(theme)
    expect(Standby).toBeTypeOf('function')
    act(() => useStore.getState().setStandby('screensaver'))
    const { container } = render(createElement(Standby))
    await waitFor(() => expect(container.textContent).toContain('Chrono Trigger'))
    expect(container.querySelector(`.crt-standby.${theme}-standby`)).not.toBeNull()
    expect(container.textContent).toContain('Now on the TV')
    expect(container.querySelectorAll('video')).toHaveLength(2)
  })

  it('stops the videos when the stage leaves the screensaver', async () => {
    const Standby = await standbyOf(theme)
    act(() => useStore.getState().setStandby('screensaver'))
    const { container } = render(createElement(Standby))
    await waitFor(() => expect(container.querySelectorAll('video')).toHaveLength(2))
    act(() => useStore.getState().setStandby('sleep'))
    expect(container.querySelector('video')).toBeNull()
    expect(container.querySelector('.crt-standby-sleep')).not.toBeNull()
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled()
    act(() => useStore.getState().setStandby('off'))
    expect(container.innerHTML).toBe('')
  })
})

it('orbit plays its favourites more often', async () => {
  localStorage.setItem('orbit-favourites', JSON.stringify(['gba:Golden Sun (Europe).gba']))
  const Standby = await standbyOf('orbit')
  act(() => useStore.getState().setStandby('screensaver'))
  render(createElement(Standby))
  await waitFor(() => expect(api.standby.videos).toHaveBeenCalledWith(['gba:Golden Sun (Europe).gba']))
  localStorage.clear()
})
