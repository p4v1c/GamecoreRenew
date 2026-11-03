import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  FETCH_RELOAD_LIMIT, clearFetchReloads, isFetchFailure, reloadAfterFetchFailure,
} from './themeSafety'

describe('a theme download that fails at boot', () => {
  beforeEach(() => { sessionStorage.clear(); vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('is told apart from a theme that throws', () => {
    expect(isFetchFailure(new TypeError(
      'Failed to fetch dynamically imported module: http://127.0.0.1:8765/themes/orbit/index.js'))).toBe(true)
    expect(isFetchFailure(new TypeError("Cannot read properties of undefined (reading 'map')"))).toBe(false)
    expect(isFetchFailure(new Error('theme entry must default-export a function'))).toBe(false)
  })

  it('reloads the page, a limited number of times', () => {
    const reload = vi.fn()
    for (let i = 0; i < FETCH_RELOAD_LIMIT; i++) expect(reloadAfterFetchFailure(reload)).toBe(true)
    expect(reloadAfterFetchFailure(reload)).toBe(false)
    vi.runAllTimers()
    expect(reload).toHaveBeenCalledTimes(FETCH_RELOAD_LIMIT)
  })

  it('gets its retries back once a theme has loaded', () => {
    for (let i = 0; i < FETCH_RELOAD_LIMIT; i++) reloadAfterFetchFailure(() => {})
    clearFetchReloads()
    expect(reloadAfterFetchFailure(() => {})).toBe(true)
  })
})
