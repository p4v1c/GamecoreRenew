import React, { createContext, useContext } from 'react'
import ErrorBoundary from './ErrorBoundary'
import type { SurfaceName } from '../lib/themeLoader'
import type { ThemeState } from '../hooks/useTheme'

const ThemeCtx = createContext<ThemeState | null>(null)

export function ThemeProvider({ value, children }: { value: ThemeState; children: React.ReactNode }) {
  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>
}

export function useThemeCtx(): ThemeState | null {
  return useContext(ThemeCtx)
}

/**
 * Renders the theme's version of a surface, or the default one.
 *
 * The boundary is per surface on purpose: a theme that breaks its library
 * screen keeps its dashboard, and the user can still reach Settings to switch
 * back. Falling back also records the crash, which is what eventually makes the
 * loader refuse the theme entirely.
 */
export function Surface<P extends object>({ name, fallback: Fallback, ...props }: {
  name: SurfaceName
  fallback: React.ComponentType<P>
} & P) {
  const theme = useThemeCtx()
  const Themed = theme?.surfaces?.[name]
  const rest = props as unknown as P

  if (!Themed) return <Fallback {...rest} />

  return (
    <ErrorBoundary
      resetKey={theme?.resetKey}
      fallback={<Fallback {...rest} />}
      onError={() => theme?.noteSurfaceCrash(name)}
    >
      <Themed {...(rest as object)} />
    </ErrorBoundary>
  )
}
