/**
 * The dashboard, walked fast — the same defect the library had, one screen up.
 *
 * Not what was reported: the report was about the shelf. It is here because the
 * cause is the same one and it was found looking for that one. `navigate` read
 * the focused card and the current page out of the closure the handler was
 * registered with, so every press that arrived before React had re-rendered
 * started from the previous press's starting point and set the same index
 * again. Three taps moved the cursor one card, and paging past the last column
 * was worse: the second tap of a pair re-paged from the page before.
 *
 * ✕ had the same window, and there it is not a lost press but a wrong one: the
 * card it opened came from the page and focus of the last render, so a confirm
 * landing right after a move could open the card the player had just left.
 */
import { render, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useStore } from '../../store'
import HomeScreen from './index'

/** Three pages of the default 4 × 2 grid, and a partial fourth. */
const SYSTEMS = Array.from({ length: 26 }, (_, i) => ({
  id: `sys${String(i).padStart(2, '0')}`,
  label: `System ${i}`,
  color: '#6a5acd',
  kind: 'emulator',
}))

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(typeof input === 'string' ? input : (input as Request).url ?? input)
    const body: unknown = /\/systems$/.test(url.split('?')[0]) ? SYSTEMS : []
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
  useStore.setState({
    screen: 'home', gridFocusIdx: 0, gridPage: 0,
    modalDepth: 0, sessionGameKey: null, selectedSystemId: null,
  })
})

afterEach(async () => {
  const { cleanup } = await import('@testing-library/react')
  cleanup()
  vi.unstubAllGlobals()
})

async function mount() {
  const r = render(<HomeScreen onLaunchApp={() => {}} />)
  await act(async () => { await new Promise(res => setTimeout(res, 0)) })
  return r
}

const burst = async (event: string, n: number) => {
  await act(async () => {
    for (let i = 0; i < n; i++) window.dispatchEvent(new CustomEvent(event))
  })
}

const at = () => {
  const s = useStore.getState()
  return { page: s.gridPage, focus: s.gridFocusIdx }
}

describe('the dashboard cursor under a burst of presses', () => {
  it('moves one card per press across a row', async () => {
    await mount()
    await burst('gp:dpad-right', 3)
    expect(at()).toEqual({ page: 0, focus: 3 })
  })

  it('carries a burst over the end of a page', async () => {
    // Four cards across, so the fourth press is a page turn and the fifth is a
    // step on the new page. Both were lost, and the page turn was lost twice
    // over: a second press still on the old page turned the same page again.
    await mount()
    await burst('gp:dpad-right', 5)
    expect(at()).toEqual({ page: 1, focus: 1 })
    await burst('gp:dpad-right', 2)
    expect(at()).toEqual({ page: 1, focus: 3 })
  })

  it('comes back the way it went', async () => {
    // Six out and four back is two out, page turns included.
    await mount()
    await burst('gp:dpad-right', 6)
    await burst('gp:dpad-left', 4)
    expect(at()).toEqual({ page: 0, focus: 2 })
  })

  it('turns pages one per press on L1 and R1', async () => {
    await mount()
    await burst('gp:r1', 3)
    expect(at()).toEqual({ page: 3, focus: 0 })
    await burst('gp:l1', 2)
    expect(at()).toEqual({ page: 1, focus: 0 })
  })

  it('stops at the last card rather than running off a short page', async () => {
    // 26 systems in a 4 × 2 grid: the fourth page holds two.
    await mount()
    await burst('gp:r1', 9)
    expect(at().page).toBe(3)
    await burst('gp:dpad-right', 6)
    expect(at()).toEqual({ page: 3, focus: 1 })
  })

  it('opens the card the cursor is actually on, not the one it was on', async () => {
    // The half of this that is not a lost press. ✕ resolved its card from the
    // page and focus of the last render, so a confirm arriving in the same
    // window as a move opened the wrong system.
    await mount()
    // Five steps right from the first card is the second card of page two —
    // right at the end of a row turns the page, it does not wrap to the row
    // below, which is what ↓ is for.
    await burst('gp:dpad-right', 5)
    await burst('gp:confirm', 1)
    expect(useStore.getState().selectedSystemId).toBe('sys09')
    expect(useStore.getState().screen).toBe('library')
  })
})
