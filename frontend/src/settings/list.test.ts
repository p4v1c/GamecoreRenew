/**
 * `versionLabel` — one `v`, whatever the box answered.
 *
 * An installed box's VERSION is the release tag, `v1.2.60`, and the settings
 * rail, the System page and its update line all printed `v${version}`: the
 * owner read "vv1.2.60" on the TV.
 */
import { describe, expect, it } from 'vitest'

// Through a variable path, like the other tests of these plain .js modules:
// `npm run build` typechecks this file and list.js has no declarations.
const LIST = './list.js'
const { versionLabel } = await import(/* @vite-ignore */ LIST) as { versionLabel: (v?: string) => string }

describe('versionLabel', () => {
  it('shows one v whether or not the box wrote one', () => {
    expect(versionLabel('v1.2.60')).toBe('v1.2.60')
    expect(versionLabel('1.2.60')).toBe('v1.2.60')
    expect(versionLabel('V1.2.60')).toBe('v1.2.60')
  })

  it('shows nothing rather than a bare v when there is no version', () => {
    expect(versionLabel('')).toBe('')
    expect(versionLabel(undefined)).toBe('')
  })
})
