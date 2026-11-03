import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../lib/themeLoader', () => ({
  clearThemeStyles: vi.fn(),
  setActiveTheme: vi.fn(),
  fetchThemeIndex: vi.fn(async () => ({
    active: 'orbit', sdk_version: 9,
    themes: [{ id: 'orbit', compatible: true, api: 9 }],
  })),
  loadTheme: vi.fn(async () => {
    throw new TypeError('Failed to fetch dynamically imported module: http://127.0.0.1:8765/themes/orbit/index.js')
  }),
}))

import { useTheme } from './useTheme'
import { crashCount } from '../lib/themeSafety'

describe('a theme whose files could not be downloaded', () => {
  beforeEach(() => { localStorage.clear(); sessionStorage.clear() })
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

  it('is retried, not counted as a crash', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout'] })
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload })
    const { result } = renderHook(() => useTheme())
    await vi.waitFor(() => expect(sessionStorage.getItem('gc:theme:fetchReloads')).toBe('1'))
    vi.runAllTimers()
    expect(reload).toHaveBeenCalledOnce()
    expect(crashCount('orbit')).toBe(0)
    expect(result.current.loading).toBe(true)
  })

  it('falls back like any failure once the retries are spent', async () => {
    sessionStorage.setItem('gc:theme:fetchReloads', '3')
    const { result } = renderHook(() => useTheme())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.themeId).toBeNull()
    expect(crashCount('orbit')).toBe(1)
  })
})
