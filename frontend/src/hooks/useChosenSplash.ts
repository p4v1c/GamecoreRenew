import { useRef } from 'react'

/**
 * The boot animation to mount: the theme's, or `fallback` if it draws none.
 *
 * Frozen while a splash is on screen, so a theme resolving mid-boot never swaps
 * animations under the player. Between splashes it follows the theme: a wake
 * replays the splash, and the one latched at page load belonged to a theme
 * whose stylesheet a switch had removed (an unstyled giant logo, no animation).
 * Null until the theme first resolves.
 */
export function useChosenSplash<T>(splash: T | undefined, loading: boolean, showing: boolean, fallback: T): T | null {
  const chosen = useRef<T | null>(null)
  if (!loading && (!chosen.current || !showing)) chosen.current = splash ?? fallback
  return chosen.current
}
