/**
 * The bezel window, and the one thing it must refuse to draw.
 *
 * This screen is the last step of the cascade. Everything upstream can be
 * right — the pack resolved, the hole measured — and the player still sees the
 * wrong thing if this component decides on its own what to paint.
 *
 * Two rules are load-bearing here, and both fail silently.
 *
 * The bezel comes from the event, not from `system_id`. Building the URL here
 * was correct while there was one PNG per system; with a per-game pack it
 * throws the resolution away one process boundary before it is used, and every
 * game gets the system bezel. That looks exactly like a pack that did not
 * install.
 *
 * And the drawn fallback frame stands in for a bezel that FAILED TO LOAD, never
 * for a bezel that does not exist. A system nobody cut artwork for would
 * otherwise get four black rectangles positioned by a hole nobody measured,
 * over a game that was filling the screen correctly.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act, cleanup } from '@testing-library/react'
import OverlayScreen from './index'

type OverlayData = {
  system_id: string
  rect?: { x: number; y: number; w: number; h: number }
  asset?: string | null
  source?: string
}

const listeners: Record<string, ((d: OverlayData) => void) | undefined> = {}

beforeEach(() => {
  for (const k of Object.keys(listeners)) delete listeners[k]
  ;(window as unknown as { gamecore: unknown }).gamecore = {
    onOverlayShow:    (cb: (d: OverlayData) => void) => { listeners.show = cb },
    onOverlayHide:    (cb: (d: OverlayData) => void) => { listeners.hide = cb },
    onOverlayWaiting: (cb: (d: OverlayData) => void) => { listeners.waiting = cb },
  }
})

afterEach(() => {
  cleanup()
  delete (window as { gamecore?: unknown }).gamecore
  vi.restoreAllMocks()
})

function show(data: OverlayData) {
  const view = render(<OverlayScreen />)
  act(() => { listeners.show?.(data) })
  return view
}

const HOLE = { x: 240, y: 0, w: 1440, h: 1080 }

/** The four rectangles the component draws when it has no image to show.
 *
 *  Counted through the CSSOM and not with an attribute-substring selector:
 *  jsdom normalises `rgba(9,9,15,0.95)` to `rgba(9, 9, 15, 0.95)`, so
 *  `div[style*="rgba(9,9,15,0.95)"]` matches nothing — and every assertion
 *  that a frame is ABSENT would then pass without checking anything. The root
 *  element's background is `transparent`, so it never counts.
 */
function maskCount(container: HTMLElement): number {
  return Array.from(container.querySelectorAll('div'))
    .filter(d => d.style.background.startsWith('rgba')).length
}

describe('which bezel gets drawn', () => {
  it('draws the asset the launch resolved to, not one built from system_id', () => {
    const { container } = show({
      system_id: 'duckstation',
      asset: '/assets/overlays/duckstation/Crash%20Bandicoot%20%28USA%29.png',
      source: 'game',
      rect: HOLE,
    })
    const img = container.querySelector('img')
    expect(img?.getAttribute('src'))
      .toBe('/assets/overlays/duckstation/Crash%20Bandicoot%20%28USA%29.png')
  })

  it('gives two games on one system two different bezels', () => {
    const { container, rerender } = show({
      system_id: 'duckstation', source: 'game', rect: HOLE,
      asset: '/assets/overlays/duckstation/Crash.png',
    })
    const first = container.querySelector('img')?.getAttribute('src')

    rerender(<OverlayScreen />)
    act(() => {
      listeners.show?.({
        system_id: 'duckstation', source: 'game', rect: HOLE,
        asset: '/assets/overlays/duckstation/Silent%20Hill.png',
      })
    })
    expect(container.querySelector('img')?.getAttribute('src')).not.toBe(first)
  })

  it('falls back to the per-system path when the event carries no asset field', () => {
    // An Electron main process older than the resolver. An update that lands
    // in the wrong order must still show the bezel it showed yesterday.
    const { container } = show({ system_id: 'pcsx2', rect: HOLE })
    expect(container.querySelector('img')?.getAttribute('src'))
      .toBe('/assets/overlays/pcsx2.png')
  })
})

describe('what happens when there is no bezel', () => {
  it('draws nothing at all — no image and no frame', () => {
    // `asset: null` is the cascade saying it found nothing, which is the
    // normal answer for the five 16:9 systems.
    const { container } = show({ system_id: 'rpcs3', asset: null, source: 'none' })
    expect(container.querySelector('img')).toBeNull()
    expect(maskCount(container)).toBe(0)
  })

  it('still draws nothing when a hole is offered alongside', () => {
    // The dangerous shape: geometry present, artwork absent. Drawing the frame
    // here is how a game that filled the screen acquires black bars.
    const { container } = show({ system_id: 'rpcs3', asset: null, rect: HOLE })
    expect(maskCount(container)).toBe(0)
  })

  it('draws the frame when a bezel exists but fails to load', () => {
    // This is what the fallback is for: the PNG is on the box, the img tag
    // errored, and the measured hole is still the right place for the game.
    const { container } = show({
      system_id: 'duckstation', asset: '/assets/overlays/duckstation.png', rect: HOLE,
    })
    act(() => {
      container.querySelector('img')?.dispatchEvent(new Event('error'))
    })
    expect(maskCount(container)).toBe(4)
  })
})

describe('the launching state', () => {
  it('shows the spinner while the emulator window is being waited for', () => {
    render(<OverlayScreen />)
    act(() => { listeners.waiting?.({ system_id: 'duckstation' }) })
    expect(document.body.textContent).toContain('Launching')
  })

  it('disappears when the game ends', () => {
    const { container } = show({
      system_id: 'duckstation', asset: '/assets/overlays/duckstation.png', rect: HOLE,
    })
    act(() => { listeners.hide?.({ system_id: 'duckstation' }) })
    expect(container.querySelector('img')).toBeNull()
    expect(maskCount(container)).toBe(0)
  })
})
