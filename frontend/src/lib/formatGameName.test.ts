/**
 * The tile label, derived from a ROM file name.
 *
 * This runs on every game in the library and its only input is what a dump is
 * called — which nobody here controls. The failure that matters is not an
 * ugly label: it is a title stripped down to nothing, or stripped of a word
 * that was part of the game's actual name, because the tile then reads as a
 * different game or as no game at all.
 */
import { describe, expect, it } from 'vitest'
import { formatGameName } from './formatGameName'

describe('what it removes', () => {
  it.each([
    ['Super Metroid USA', 'Super Metroid'],
    ['Chrono Trigger Japan', 'Chrono Trigger'],
    ['Sonic the Hedgehog Europe', 'Sonic the Hedgehog'],
    ['Some Game World', 'Some Game'],
    ['Some Game International', 'Some Game'],
    ['Some Game Rev 1', 'Some Game'],
    ['Some Game v1.2', 'Some Game'],
  ])('drops the trailing region of %j', (raw, expected) => {
    expect(formatGameName(raw)).toBe(expected)
  })

  it('drops a run of language codes', () => {
    expect(formatGameName('Some Game EnFrDe')).toBe('Some Game')
  })

  it('drops a region and the language codes that follow it', () => {
    // They arrive in that order in real dump names, which is why the strip
    // runs twice.
    expect(formatGameName('Some Game Europe EnFrDe')).toBe('Some Game')
  })

  it('turns underscores back into spaces', () => {
    expect(formatGameName('Some_Game_Title')).toBe('Some Game Title')
  })

  it('trims the whitespace a strip leaves behind', () => {
    expect(formatGameName('  Some Game USA  ')).toBe('Some Game')
  })
})

describe('what it must never remove', () => {
  it('keeps a name that is only a region word', () => {
    // The regex needs whitespace before the region, so a one-word title
    // survives. A tile with an empty label is unclickable and unsearchable.
    expect(formatGameName('Japan')).toBe('Japan')
  })

  it('leaves a title with no region markers alone', () => {
    expect(formatGameName('The Legend of Zelda')).toBe('The Legend of Zelda')
  })

  it('keeps a region word that is part of the title', () => {
    // Only the TRAILING one goes.
    expect(formatGameName('Europe Racing Championship')).toBe(
      'Europe Racing Championship')
  })

  it('never returns an empty label for a non-empty name', () => {
    for (const raw of ['USA', 'Europe', 'World', 'En', 'Rev 1', 'v1.0']) {
      expect(formatGameName(raw).length).toBeGreaterThan(0)
    }
  })

  it('handles an empty name without throwing', () => {
    expect(formatGameName('')).toBe('')
  })
})
