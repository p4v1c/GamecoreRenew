import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useChosenSplash } from './useChosenSplash'

type Props = { splash?: string; loading: boolean; showing: boolean }
const setup = (initial: Props) =>
  renderHook(({ splash, loading, showing }: Props) => useChosenSplash(splash, loading, showing, 'default'),
             { initialProps: initial })

describe('the boot animation to mount', () => {
  it('waits for the theme, then never swaps mid-boot', () => {
    const { result, rerender } = setup({ loading: true, showing: true })
    expect(result.current).toBeNull()
    rerender({ splash: 'orbit', loading: false, showing: true })
    expect(result.current).toBe('orbit')
    rerender({ splash: 'summer', loading: false, showing: true })
    expect(result.current).toBe('orbit')
  })

  it('a wake after a theme switch plays the new theme, not the one the page booted on', () => {
    const { result, rerender } = setup({ splash: 'orbit', loading: false, showing: true })
    rerender({ splash: 'orbit', loading: false, showing: false })     // boot over
    rerender({ splash: 'orbit', loading: true, showing: false })      // switch in flight
    rerender({ splash: 'summer', loading: false, showing: false })
    rerender({ splash: 'summer', loading: false, showing: true })     // wake
    expect(result.current).toBe('summer')
  })

  it('falls back to the default when the theme draws none', () => {
    const { result } = setup({ loading: false, showing: true })
    expect(result.current).toBe('default')
  })
})
