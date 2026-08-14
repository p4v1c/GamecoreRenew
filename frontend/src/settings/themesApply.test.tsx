/**
 * "Applying…", and the case where it never ends.
 *
 * Selecting a theme is meant to end by this screen ceasing to exist: the shell
 * swaps and takes the settings screen with it. So the page set `busy` and only
 * cleared it when the promise rejected.
 *
 * The promise does not reject when the chosen theme fails to LOAD. The request
 * succeeds, the box records the choice, and `ThemeSurface.Shell` renders the
 * built-in fallback bare — no key, so nothing remounts and this component is
 * still mounted, spinning, over a screen that has already given up.
 */
import { render, screen, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { buildSdk } from '../lib/themeSdk'
import { createThemesPage } from '../settings/themes'
import { createRows } from '../settings/rows'

const INDEX = {
  sdk_version: 2, active: null,
  themes: [{ id: 'shelf', name: 'Shelf', version: '3.2.2', api: 2, compatible: true,
             description: 'boxes on a wall', warnings: [] }],
}

const mount = (selectTheme: (id: string | null) => Promise<void>) => {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200, statusText: 'OK', json: async () => INDEX,
  })))
  const sdk = buildSdk('', { selectTheme })
  const Page = createThemesPage(sdk, createRows(sdk)) as unknown as
    React.ComponentType<{ active: boolean; onLeave: () => void }>
  return render(<Page active onLeave={() => {}} />)
}

const applyShelf = async (c: HTMLElement) => {
  await waitFor(() => expect(c.textContent).toContain('Shelf'))
  const row = [...c.querySelectorAll('.gcs-row2')]
    .find(r => r.textContent?.includes('Shelf')) as HTMLElement
  await act(async () => { row.click() })
}

beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }) })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('applying a theme', () => {
  it('gives the button back and says so when the shell never swaps', async () => {
    // Resolves, like a successful selection — and then nothing happens,
    // because the theme threw while loading and the fallback shell has no key
    // to remount on.
    const { container } = mount(async () => {})
    await applyShelf(container)
    expect(container.textContent).toContain('Applying…')

    await act(async () => { vi.advanceTimersByTime(7000) })

    expect(container.textContent).not.toContain('Applying…')
    // Not "failed": the box did record the choice, and it will be there at the
    // next start. What did not happen is the swap.
    expect(screen.getByText(/did not switch to it/)).toBeTruthy()
  })

  it('reports a refusal immediately rather than waiting the timeout out', async () => {
    const { container } = mount(async () => { throw new Error('nope') })
    await applyShelf(container)
    await waitFor(() => expect(screen.getByText(/Could not apply/)).toBeTruthy())
    expect(container.textContent).not.toContain('Applying…')
  })

  it('does not give up on a selection that is still swapping', async () => {
    // A theme that is going to load has swapped the shell long before the
    // deadline; the button must stay busy until then rather than flash an
    // error over a switch that is working.
    const { container } = mount(() => new Promise(() => {}))
    await applyShelf(container)
    await act(async () => { vi.advanceTimersByTime(3000) })
    expect(container.textContent).toContain('Applying…')
  })
})
