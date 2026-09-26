/**
 * The built-in settings screen — the same one Shelf and Summer draw
 * (`src/settings/`, palette from settings.css). This file only builds the SDK
 * that screen expects.
 *
 * `buildSdk` gets an empty theme id (no theme assets are loaded here), but a
 * REAL `selectTheme`: safe mode lands players here after a theme crash, and
 * the Themes page is their way out.
 * The screen lives in the bundle, not in an OTA-delivered theme folder, so the
 * safe-mode fallback cannot share a theme's failure.
 */
import { useMemo, useRef, useEffect } from 'react'
import { buildSdk } from '../../lib/themeSdk'
import { createSettings } from '../../settings/screen'
import { useThemeCtx } from '../ThemeSurface'
import '../../settings/settings.css'

export default function SettingsScreen({ onClose }: { onClose: () => void }) {
  // The context, never `useTheme()` directly: that hook IS the theme state
  // machine, and calling it a second time would start a second one — loading
  // the active theme again behind the screen the player is standing on.
  const theme = useThemeCtx()

  // The sdk is built once (below) and would otherwise capture whichever
  // `select` existed on first render. Same ordering gap the loader closes the
  // same way.
  //
  // The context is nullable — this screen renders in tests and in the shot
  // harness with no provider above it. Falling back to a no-op keeps the Themes
  // page rendering there instead of taking the screen down; on a real box the
  // provider is always present.
  const selectRef = useRef(theme?.select)
  useEffect(() => { selectRef.current = theme?.select }, [theme?.select])

  /**
   * Built once. `createSettings` calls every page factory it has, so rebuilding
   * it on a render would hand the screen a new component identity each time and
   * remount all nine pages — losing whatever the player had typed or scrolled.
   */
  const Screen = useMemo(() => {
    const sdk = buildSdk('', {
      selectTheme: async (id) => { await selectRef.current?.(id) },
    })
    // `skin` is the class that carries this surface's colours; see settings.css
    // for why it is a class and not `:root`. No TopBar: a theme puts its own
    // above the rail, and the built-in UI's belongs to the home screen.
    return createSettings(sdk, {}, { skin: 'gcs-skin-default' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <Screen onClose={onClose} />
}
