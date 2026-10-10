/**
 * Jelly's standby as the Shell gets it: mounted only in the `screensaver`
 * stage, jellies holding covers, one clip at a time in the featured jelly,
 * everything stopped and emptied when the stage moves on. Frames are pumped
 * by hand; what it looks like is checked in a browser (docs/dev-log).
 */
import { createElement } from 'react'
import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { buildSdk } from '../lib/themeSdk'
import { api } from '../api'
import { useStore } from '../store'

const THEME = '../../../config/themes/jelly'
const item = (system_id: string, filename: string, display_name: string, media_type = 'video-normalized') => ({
  system_id, filename, display_name, system_name: 'Game Boy Advance', last_played: null, media_type,
  url: `/api/media/${system_id}/${encodeURIComponent(filename)}/media/${media_type}`,
})
const PLAYLIST = {
  videos: [item('gba', 'Golden Sun (Europe).gba', 'Golden Sun')],
  stills: [item('gba', 'Metroid Fusion (Europe).gba', 'Metroid Fusion', 'screenshot-gameplay'),
    item('gba', 'Wario Land 4 (Europe).gba', 'Wario Land 4', 'screenshot-gameplay')],
}

let frames: FrameRequestCallback[] = []
let clock = 0
/** Run `seconds` of 50 ms frames (the engine's dt cap). */
const pump = (seconds: number) => act(() => {
  for (let i = 0; i < seconds * 20; i++) {
    const due = frames
    frames = []
    clock += 50
    due.forEach((cb) => cb(clock))
  }
})

/** jsdom loads no images: every cover "loads" on the next tick. */
class LoadingImage {
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  naturalWidth = 300
  set src(_v: string) { setTimeout(() => this.onload?.()) }
}

const reducedMotion = (on: boolean) => vi.stubGlobal('matchMedia', (q: string) => ({
  matches: on && q.includes('reduce'), media: q, addEventListener() {}, removeEventListener() {},
}))

beforeEach(() => {
  frames = []
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => { frames.push(cb); return frames.length })
  vi.stubGlobal('cancelAnimationFrame', () => { frames = [] })
  vi.stubGlobal('Image', LoadingImage)
  reducedMotion(false)
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
  vi.spyOn(api.standby, 'videos').mockResolvedValue(PLAYLIST)
  vi.spyOn(api.standby, 'exit').mockResolvedValue({ ok: true } as never)
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  act(() => useStore.getState().setStandby('off'))
})

/** Jelly's `screensaver` part, as it hands it to the Shell. */
async function standbyOf(sdk = buildSdk('jelly', { selectTheme: vi.fn(async () => {}) })) {
  let parts: Record<string, unknown> = {}
  const defaults = { ...sdk.defaults, Shell: (p: Record<string, unknown>) => { parts = p; return null } }
  const mod = await import(/* @vite-ignore */ `${THEME}/index.js`)
  render(createElement(mod.default({ ...sdk, defaults }).shell))
  cleanup()
  return parts.screensaver as React.ComponentType | undefined
}

async function mounted() {
  const Standby = (await standbyOf())!
  act(() => useStore.getState().setStandby('screensaver'))
  const view = render(createElement(Standby))
  await waitFor(() => expect(view.container.querySelectorAll('.jl-sb-blob')).toHaveLength(3))
  return view
}

describe('jelly standby', () => {
  it('is nothing outside standby', async () => {
    const Standby = (await standbyOf())!
    const { container } = render(createElement(Standby))
    expect(container.innerHTML).toBe('')
  })

  it('fills the floor with one jelly per game, each holding its cover, and names one', async () => {
    const { container } = await mounted()
    const covers = [...container.querySelectorAll<HTMLImageElement>('.jl-sb-blob .jl-sb-cover')]
    expect(covers.map((c) => decodeURIComponent(c.src))).toEqual(expect.arrayContaining([
      expect.stringContaining('/api/covers/gba/Golden Sun (Europe).gba')]))
    await waitFor(() => expect(container.querySelector('.jl-sb-caption')?.getAttribute('data-empty')).toBe('false'))
    expect(container.textContent).toContain('Wobbling now')
    expect(container.textContent).toContain('Game Boy Advance')
    expect(container.querySelector('video')).toBeNull()
  })

  it('features the clip in a jelly, then lets it go; one video at most', async () => {
    const { container } = await mounted()
    pump(10)
    expect(container.querySelector('.jl-standby')?.getAttribute('data-phase')).toBe('show')
    const videos = container.querySelectorAll('video')
    expect(videos).toHaveLength(1)
    expect(videos[0].closest('.jl-sb-blob')?.classList.contains('is-featured')).toBe(true)
    expect(videos[0].getAttribute('src')).toBe(PLAYLIST.videos[0].url)
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled()
    expect(container.querySelector('.jl-sb-title')?.textContent).toBe('Golden Sun')
    act(() => { videos[0].dispatchEvent(new Event('ended')) })
    pump(3)
    expect(container.querySelector('video')).toBeNull()
    expect(container.querySelector('.jl-standby')?.getAttribute('data-phase')).toBe('swarm')
  })

  it('pops a jelly and wobbles another in', async () => {
    const { container } = await mounted()
    pump(5.5)
    expect(container.querySelector('.jl-sb-splat')).not.toBeNull()
  })

  it('stops and empties everything when the stage leaves the screensaver', async () => {
    const { container } = await mounted()
    pump(10)
    const video = container.querySelector('video')!
    act(() => useStore.getState().setStandby('sleep'))
    expect(container.querySelector('.jl-standby')).toBeNull()
    expect(container.querySelector('.jl-standby-sleep')).not.toBeNull()
    expect(video.isConnected).toBe(false)
    expect(video.getAttribute('src')).toBeNull()
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled()
    expect(frames).toHaveLength(0)
    act(() => useStore.getState().setStandby('off'))
    expect(container.innerHTML).toBe('')
  })

  it('holds still under reduced motion: no frame loop, the feature fades on a still jelly', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    reducedMotion(true)
    const { container } = await mounted()
    expect(frames).toHaveLength(0)
    expect(container.querySelectorAll('.jl-sb-blob.is-still').length).toBeGreaterThanOrEqual(3)
    act(() => { vi.advanceTimersByTime(9000) })
    expect(container.querySelector('.jl-sb-stage.is-on video')).not.toBeNull()
    vi.useRealTimers()
  })

  it('wakes on a key press', async () => {
    await mounted()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
    expect(api.standby.exit).toHaveBeenCalled()
  })

  it('leaves the host its slideshow on a host before SDK 12', async () => {
    const sdk = buildSdk('jelly', { selectTheme: vi.fn(async () => {}) })
    const old = { ...sdk, defaults: { ...sdk.defaults, useLocalWake: undefined } } as unknown as typeof sdk
    expect(await standbyOf(old)).toBeUndefined()
  })
})
