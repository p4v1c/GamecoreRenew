/**
 * Settings → System → "Wait for the TV after waking": reachable and changed
 * with the pad alone, saved as `wake_settle_secs`. Every theme draws this page.
 */
import { render, waitFor, act } from '@testing-library/react'
import { it, expect, vi } from 'vitest'
import { buildSdk } from '../lib/themeSdk'
import { createSystemPage } from '../settings/system'
import { createRows } from '../settings/rows'

it('shows 2.5 s by default and saves the next step on → with the pad', async () => {
  const posts: unknown[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const u = String(url)
    if (u.endsWith('/api/standby/config')) posts.push(JSON.parse(init?.body || '{}'))
    const body = u.endsWith('/api/standby')
      ? { state: 'active', enabled: true, screensaver_mins: 10, sleep_mins: 30, wake_settle_secs: 2.5 }
      : u.endsWith('/api/standby/config') ? { ok: true, wake_settle_secs: 3 } : {}
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
  const sdk = buildSdk('', { selectTheme: vi.fn(async () => {}) })
  const Page = createSystemPage(sdk, createRows(sdk)) as React.ComponentType<{ active: boolean; onLeave: () => void }>
  const { findByText } = render(<Page active onLeave={() => {}} />)
  const label = await findByText('Wait for the TV after waking')
  const row = label.closest('[aria-valuetext]') ?? label.closest('.gcs-row2')
  expect(row?.textContent).toContain('2.5 s')
  // The row is in the DOM before Rows rebinds its pad handlers (a passive
  // effect); pressing in between moved through the old one-row list on slow CI.
  await act(async () => {})

  const press = (name: string) => act(() => { window.dispatchEvent(new CustomEvent(name)) })
  for (let i = 0; i < 4; i++) press('gp:dpad-down')   // update, standby, saver, off, wake
  press('gp:dpad-right')
  await waitFor(() => expect(posts).toContainEqual({ wake_settle_secs: 3 }))
})
