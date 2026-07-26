import React, { createContext, useContext } from 'react'
import ErrorBoundary from './ErrorBoundary'
import type { ThemeState } from '../hooks/useTheme'

const ThemeCtx = createContext<ThemeState | null>(null)

export function ThemeProvider({ value, children }: { value: ThemeState; children: React.ReactNode }) {
  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>
}

export function useThemeCtx(): ThemeState | null {
  return useContext(ThemeCtx)
}

/**
 * Mounts the theme's shell, or the default one.
 *
 * There is exactly one of these. The first design substituted nine components
 * inside the host's own layout, which meant the theme and the default were
 * interleaved in one tree — and every bug came from that: a theme's background
 * painted over screens it had not replaced, its modals never joined the modal
 * stack, and default settings pages got torn out of the container they were
 * written for. One tree, one owner, none of it happens.
 *
 * The boundary is what keeps a broken theme survivable: it throws, the default
 * shell takes over, and the crash is recorded so the loader eventually refuses
 * the theme outright.
 */
export function Shell({ fallback: Fallback }: { fallback: React.ComponentType }) {
  const theme = useThemeCtx()
  const Themed = theme?.shell

  if (!Themed) return <Fallback />

  return (
    <ErrorBoundary
      resetKey={theme?.resetKey}
      fallback={<Fallback />}
      onError={() => theme?.noteShellCrash()}
    >
      <Themed />
    </ErrorBoundary>
  )
}
