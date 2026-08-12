/**
 * The built-in settings screen — the same one Shelf and Summer draw.
 *
 * ## What changed, and why it is not a rewrite
 *
 * The default UI used to have a settings screen of its own: a centred list of
 * ten rows, each opening a full-screen overlay on top of it. The two shipped
 * themes drew something else entirely — a numbered rail that never leaves, the
 * category beside it, and a third column of detail for Wi-Fi and Bluetooth —
 * and the two had nothing in common but the endpoints they called.
 *
 * They are one screen now. `src/settings/` holds it, `settings.css` gives this
 * surface its palette, and a theme gives its own. Nothing here reimplements a
 * rail: this file's whole job is to hand that screen an SDK.
 *
 * ## The SDK, built for the host itself
 *
 * The screen is written in the theme SDK's idiom, so it needs one — even when
 * no theme is active. `buildSdk` takes a theme id used only to resolve assets
 * inside a theme folder, and this screen loads none, so it is given the empty
 * string rather than a lie about which theme is running.
 *
 * `selectTheme` is real, though: the Themes page inside this screen switches
 * themes, and it is very often the reason someone opened this screen at all —
 * safe mode dropped them here because their theme crashed. Wiring it to a stub
 * would strand them on the one screen that can get them out.
 *
 * ## Why the host may not simply reuse a theme's copy
 *
 * It could not, before: the screen lived under `config/themes/_shared/`, which
 * `update/linux.sh` delivers over the air. The built-in UI is what
 * `themeSafety.ts` falls back TO, so depending on an OTA-delivered directory
 * would have made the fallback share the failure it exists to catch. Moving the
 * screen into the bundle is what made this file possible.
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
