import { it, expect, vi, beforeEach } from 'vitest'
import { installErrorReports, reportError, resetReports, MAX_REPORTS } from './reportErrors'

const posted = () => (fetch as unknown as { mock: { calls: [string, { body: string }][] } })
  .mock.calls.filter(([url]) => url === '/api/logs/ui').map(([, init]) => JSON.parse(init.body))

beforeEach(() => {
  resetReports()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })))
})

it('sends an uncaught error with where it happened', () => {
  installErrorReports(window)
  window.dispatchEvent(new ErrorEvent('error', { message: 'x is undefined', filename: '/assets/index.js', lineno: 42 }))
  expect(posted()).toEqual([{ message: 'x is undefined', source: '/assets/index.js:42' }])
})

it('stops after a page load\'s budget, so a loop cannot flood the backend', () => {
  for (let i = 0; i < MAX_REPORTS + 20; i++) reportError(`boom ${i}`)
  expect(posted()).toHaveLength(MAX_REPORTS)
})
