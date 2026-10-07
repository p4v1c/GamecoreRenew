/**
 * Favourites follow the profile in Jelly and Orbit: the primary keeps the list
 * it had before profiles, another profile starts its own, and a switch
 * re-reads the right one.
 */
import { it, expect, beforeEach } from 'vitest'
import { buildSdk } from '../lib/themeSdk'
import { useStore } from '../store'

const THEMES = '../../../config/themes'

beforeEach(() => {
  localStorage.clear()
  useStore.getState().setActiveProfile('', '')
})

for (const [theme, file, base] of [
  ['jelly', 'lib/favourites.js', 'jelly-favourites'],
  ['orbit', 'lib/catalog.js', 'orbit-favourites'],
] as const) {
  it(`${theme}: one list per profile, the primary's untouched`, async () => {
    localStorage.setItem(base, JSON.stringify(['nes:zelda.nes']))
    const fav = await import(/* @vite-ignore */ `${THEMES}/${theme}/${file}`)
    const sdk = buildSdk(theme, { selectTheme: async () => {} })
    const stop = fav.followProfiles(sdk)
    expect(fav.isFavourite('nes', 'zelda.nes')).toBe(true)

    useStore.getState().setActiveProfile('Sam', 'b0b0')
    expect(fav.isFavourite('nes', 'zelda.nes')).toBe(false)
    fav.toggleFavourite('nes', 'metroid.nes')
    expect(JSON.parse(localStorage.getItem(`${base}:b0b0`)!)).toEqual(['nes:metroid.nes'])

    useStore.getState().setActiveProfile('Max', '')
    expect(fav.isFavourite('nes', 'zelda.nes')).toBe(true)
    expect(fav.isFavourite('nes', 'metroid.nes')).toBe(false)
    expect(JSON.parse(localStorage.getItem(base)!)).toEqual(['nes:zelda.nes'])
    stop()
  })
}
