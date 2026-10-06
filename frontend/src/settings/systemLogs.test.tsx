/**
 * Settings → System → Logs: the size is shown, and purging takes two presses.
 * Every theme draws this page, so this is the one place the button lives.
 */
import { render, waitFor, fireEvent } from '@testing-library/react'
import { it, expect, vi } from 'vitest'
import { buildSdk } from '../lib/themeSdk'
import { createSystemPage } from '../settings/system'
import { createRows } from '../settings/rows'

it('shows the logs size and purges only after a confirmation', async () => {
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: { method?: string }) => {
    const method = init?.method ?? 'GET'
    if (String(url).endsWith('/api/logs')) calls.push(method)
    const body = !String(url).endsWith('/api/logs') ? {}
      : method === 'DELETE' ? { ok: true, freed: { files: 3, bytes: 2097152 } }
      : { files: 3, bytes: 2097152 }
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
  const sdk = buildSdk('shelf', { selectTheme: vi.fn(async () => {}) })
  const Page = createSystemPage(sdk, createRows(sdk)) as React.ComponentType<{ active: boolean; onLeave: () => void }>
  const { container, findByText } = render(<Page active onLeave={() => {}} />)

  const row = (await findByText('3 files, 2.0 MB')).closest('.gcs-row2') as HTMLElement
  fireEvent.click(row)
  expect(calls).not.toContain('DELETE')          // armed, not fired
  fireEvent.click(row)
  await waitFor(() => expect(calls).toContain('DELETE'))
  await waitFor(() => expect(container.textContent).toContain('Logs purged, 2.0 MB freed.'))
  expect(container.textContent).toContain('Empty')
})
