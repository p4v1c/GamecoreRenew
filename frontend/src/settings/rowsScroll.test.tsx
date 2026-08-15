/**
 * The shared settings row list, when it is longer than the column.
 *
 * `.gcs-set-main` has always been `overflow: auto`, and every host settings
 * page — Bluetooth, BIOS, Storage, Catalog — calls `scrollIntoView` on its own
 * focus change. `Rows` was the one thing drawing into that column that did not,
 * and it went unnoticed because no page built on it had ever been longer than a
 * screen. The Controllers page can be now: the autoconfig switch, its
 * exceptions row and one row per emulator take it well past a screenful, and
 * the d-pad walked the highlight into rows nobody could see — pressing ✕ on a
 * control that was not on screen.
 */
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { buildSdk } from '../lib/themeSdk'
import { createRows } from '../settings/rows'

// `createRows` is declared as returning `unknown` (see settings/index.d.ts:
// the boundary is typed, the bodies are not), so the component has to be named
// for JSX. The cast asserts the props this file actually passes, nothing more.
type RowsView = React.ComponentType<Record<string, unknown>>

/** jsdom implements no layout, so `scrollIntoView` does not exist on Element. */
const spyScroll = () => {
  const calls: Element[] = []
  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    configurable: true,
    writable: true,
    value(this: Element) { calls.push(this) },
  })
  return calls
}

const list = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    id: `r${i}`, type: 'info', label: `Row ${i}`, display: 'x',
  }))

const draw = (rows: ReturnType<typeof list>, active = true) => {
  const sdk = buildSdk('', { selectTheme: vi.fn(async () => {}) })
  const Rows = createRows(sdk) as RowsView
  return render(<Rows rows={rows} active={active} title="T"
    onLeave={() => {}} onSet={() => {}} onAct={() => {}} />)
}

beforeEach(() => { cleanup() })

describe('keeping the cursor on screen', () => {
  it('scrolls the focused row into view when the cursor moves', () => {
    const calls = spyScroll()
    draw(list(20))
    calls.length = 0

    fireEvent.click(screen.getByText('Row 7').closest('.gcs-row2')!)

    // The row itself, not the container: `block: 'nearest'` on the element is
    // what scrolls the minimum needed, so a list that already fits never moves.
    expect(calls).toContain(screen.getByText('Row 7').closest('.gcs-row2'))
  })

  it('leaves the column alone while this half does not have the cursor', () => {
    // The rail has focus. Scrolling the page under it would move content the
    // player is not driving.
    const calls = spyScroll()
    draw(list(20), false)
    expect(calls).toHaveLength(0)
  })

  it('does not strand the cursor past the end when the list shrinks', () => {
    // Collapsing the per-emulator exceptions is the first list on this screen
    // that can shrink under the cursor. `fire()` reads `rows[idx]` and silently
    // does nothing when that is undefined, so the symptom is a screen where ✕
    // has stopped working and nothing says why.
    const act = vi.fn()
    const sdk = buildSdk('', { selectTheme: vi.fn(async () => {}) })
    const Rows = createRows(sdk) as RowsView
    const rows = Array.from({ length: 6 }, (_, i) => ({
      id: `a${i}`, type: 'action', label: `Act ${i}`,
    }))
    const { rerender } = render(<Rows rows={rows} active title="T"
      onLeave={() => {}} onSet={() => {}} onAct={act} />)

    fireEvent.click(screen.getByText('Act 5').closest('.gcs-row2')!)
    expect(act).toHaveBeenCalledWith('a5')

    rerender(<Rows rows={rows.slice(0, 2)} active title="T"
      onLeave={() => {}} onSet={() => {}} onAct={act} />)

    // Asserted on the highlight, not by clicking: a click sets the focus on the
    // way in and would pass with or without the clamp. `data-on="1"` is the
    // cursor, and `gp:confirm` reads the same index — no highlighted row means
    // ✕ has nothing to fire.
    const focused = document.querySelectorAll('.gcs-row2[data-on="1"]')
    expect(focused).toHaveLength(1)
    expect(focused[0].textContent).toContain('Act 1')
  })
})
