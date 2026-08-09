/**
 * The helpers `sdk.format` hands to a theme.
 *
 * These exist because writing the default UI back as an ordinary theme found
 * that a themed dashboard could not colour a system and a themed library could
 * not name a game. Both were reachable only from the default views.
 *
 * `systemColor` is the one with real logic, and the one a theme would most
 * plausibly reimplement wrongly: reading `system.color` looks sufficient right
 * up until a system that has none.
 */
import { describe, expect, it } from 'vitest'
import { systemColor } from './format'
import { SYSTEM_COLORS } from './systemColors'

describe('systemColor', () => {
  it("prefers the system's own colour", () => {
    expect(systemColor({ id: 'rpcs3', color: '#abcdef' })).toBe('#abcdef')
  })

  it('falls back to the catalogue colour when the entry has none', () => {
    // The case a theme gets wrong. `color` is optional on SystemEntry and is
    // absent for anything the catalogue does not describe, so a view reading
    // it alone paints those systems the house purple and looks broken rather
    // than plain.
    const id = Object.keys(SYSTEM_COLORS)[0]
    expect(systemColor({ id, color: undefined })).toBe(SYSTEM_COLORS[id])
  })

  it('matches the catalogue case-insensitively', () => {
    const id = Object.keys(SYSTEM_COLORS)[0]
    expect(systemColor({ id: id.toUpperCase(), color: undefined })).toBe(SYSTEM_COLORS[id])
  })

  it('falls back to the house accent for a system nobody has described', () => {
    expect(systemColor({ id: 'no-such-system', color: undefined })).toBe('#7c3aed')
  })

  it('does not fall over on an empty id', () => {
    // LibraryScreen resolves the colour before the system has loaded, so this
    // is a real state and not a defensive flourish.
    expect(systemColor({ id: '', color: undefined })).toBe('#7c3aed')
  })
})
