/** The legacy list's Logs page: a purge takes two presses, like the rail's. */
import { render, fireEvent, waitFor } from '@testing-library/react'
import { it, expect, vi } from 'vitest'
import { LogsPage } from './LogsPage'

it('purges only on the second press', async () => {
  const methods: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: { method?: string }) => {
    if (String(url).endsWith('/api/logs')) methods.push(init?.method ?? 'GET')
    const body = init?.method === 'DELETE' ? { ok: true, freed: { files: 2, bytes: 1048576 } } : { files: 2, bytes: 1048576 }
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
  const { findByText, container } = render(<LogsPage onClose={() => {}} onBack={() => {}} />)
  await findByText('2 files, 1.0 MB')

  fireEvent.click(await findByText('✕ Purge logs'))
  expect(methods).not.toContain('DELETE')
  fireEvent.click(await findByText('Press ✕ again to purge logs'))
  await waitFor(() => expect(container.textContent).toContain('Logs purged, 1.0 MB freed.'))
  expect(methods).toContain('DELETE')
})
