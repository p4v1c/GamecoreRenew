/** Player 1 is shown by the active profile's name; every other slot is P<n>. */
import { it, expect } from 'vitest'
import { controllerTitle, playerLabel, playerTitle } from './players'

it('names player 1 after the profile once the box has profiles', () => {
  expect(playerLabel(1, 'Max')).toBe('Max')
  expect(playerTitle(1, 'Max')).toBe('Max')
  expect(controllerTitle(1, 'Max')).toBe('Max’s controller')
})

it('keeps the numbers without profiles, and for players 2 to 4', () => {
  expect(playerLabel(1, '')).toBe('P1')
  expect(playerLabel(2, 'Max')).toBe('P2')
  expect(playerTitle(3, 'Max')).toBe('Player 3')
  expect(controllerTitle(2, 'Max')).toBe('Controller 2')
  expect(controllerTitle(null, 'Max')).toBe('Controller')
})
