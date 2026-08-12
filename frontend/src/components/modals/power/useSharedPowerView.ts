/**
 * The shared power menu, built for the host itself.
 *
 * `createPowerView` is written in the theme SDK's idiom, so it needs an sdk
 * even when no theme is active — the same arrangement as SettingsScreen, and
 * for the same reason: one implementation, three palettes.
 *
 * Built once per mount and returned as null if building it throws. PowerModal
 * falls back to the older `DefaultPowerView` in that case, because this is the
 * screen that turns the box off: an exception here must cost the player a
 * prettier menu, never the ability to shut down.
 *
 * No `selectTheme`: nothing in the power menu switches themes, and handing it a
 * real one would be widening what this screen can do for no reason.
 */
import { useMemo } from 'react'
import { buildSdk } from '../../../lib/themeSdk'
import { createPowerView } from '../../../settings/power'
import type { PowerViewProps } from './types'
import '../../../settings/settings.css'

export function useSharedPowerView(): React.ComponentType<PowerViewProps> | null {
  return useMemo(() => {
    try {
      const sdk = buildSdk('', { selectTheme: async () => {} })
      return createPowerView(sdk, { skin: 'gcs-skin-default' }) as unknown as React.ComponentType<PowerViewProps>
    } catch (e) {
      console.error('power menu: falling back to the built-in view', e)
      return null
    }
  }, [])
}
