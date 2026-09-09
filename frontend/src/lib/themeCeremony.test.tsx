import { act, cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createElement } from 'react'
import { buildSdk } from './themeSdk'
import { useStore } from '../store'

beforeEach(() => {
  vi.useFakeTimers()
  useStore.setState({ transition: null })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.useRealTimers()
  useStore.setState({ transition: null })
})

async function factory(theme: 'orbit' | 'shelf') {
  const path = `../../../config/themes/${theme}/views/ceremony.js`
  const module = await import(/* @vite-ignore */ path)
  return module.createCeremony(buildSdk(theme, { selectTheme: vi.fn(async () => {}) }))
}

describe('Orbit ceremony', () => {
  it('draws travel for launch and return for suspend', async () => {
    const Ceremony = await factory('orbit')
    const view = render(createElement(Ceremony))
    expect(view.container.querySelector('.orbit-ceremony')).toBeNull()

    act(() => { useStore.getState().setTransition('launch') })
    expect(view.container.querySelector('.orbit-ceremony')?.getAttribute('data-dir')).toBe('away')
    act(() => { useStore.getState().setTransition('suspend') })
    expect(view.container.querySelector('.orbit-ceremony')?.getAttribute('data-dir')).toBe('back')
  })

  it('keeps the final frame briefly, then removes it', async () => {
    const Ceremony = await factory('orbit')
    const view = render(createElement(Ceremony))
    act(() => { useStore.getState().setTransition('launch') })
    act(() => { useStore.getState().setTransition(null) })
    expect(view.container.querySelector('.orbit-ceremony')).toBeTruthy()
    await act(async () => { await vi.advanceTimersByTimeAsync(120) })
    expect(view.container.querySelector('.orbit-ceremony')).toBeNull()
  })
})

describe('Shelf ceremony', () => {
  it('leaves launch to the cartridge animation and draws resume and suspend', async () => {
    const Ceremony = await factory('shelf')
    const view = render(createElement(Ceremony))

    act(() => { useStore.getState().setTransition('launch') })
    expect(view.container.querySelector('.cz-handover')).toBeNull()
    act(() => { useStore.getState().setTransition('resume') })
    expect(view.container.querySelector('.cz-handover')?.getAttribute('data-move')).toBe('resume')
    act(() => { useStore.getState().setTransition('suspend') })
    expect(view.container.querySelector('.cz-handover')?.getAttribute('data-move')).toBe('suspend')
  })
})

describe('Summer ceremony', () => {
  it('uses its vortex for launch, resume and suspend', async () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as any)
    const path = '../../../config/themes/summer/views/warp.js'
    const { createWarp } = await import(/* @vite-ignore */ path)
    const Warp = createWarp(buildSdk('summer', { selectTheme: vi.fn(async () => {}) }))
    const view = render(createElement(Warp))
    const canvas = view.container.querySelector('.sm-warp') as HTMLCanvasElement
    expect(canvas.getAttribute('data-move')).toBe('none')

    act(() => { useStore.getState().setTransition('launch') })
    expect(canvas.getAttribute('data-move')).toBe('launch')
    expect(canvas.hidden).toBe(false)
    act(() => { useStore.getState().setTransition('resume') })
    expect(canvas.getAttribute('data-move')).toBe('resume')
    act(() => { useStore.getState().setTransition('suspend') })
    expect(canvas.getAttribute('data-move')).toBe('suspend')
  })
})
