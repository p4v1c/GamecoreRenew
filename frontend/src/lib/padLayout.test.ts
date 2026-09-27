import { describe, it, expect } from 'vitest'
import type { GamepadState } from '../hooks/useGamepad'
import type { RosterPad } from '../api'
import { vidPid, matchRoster, presentControls, pressedControls, missingSentence, padStatus, buildPads } from './padLayout'

const state = (over: Partial<GamepadState> = {}): GamepadState => ({
  connected: true, index: 0, id: '', mapping: 'standard',
  pressed: Array(17).fill(false), values: Array(17).fill(0), axes: [0, 0, 0, 0], ...over,
})
const gp = (index: number, id: string, mapping = 'standard') => ({ index, id, mapping } as Gamepad)
const row = (over: Partial<RosterPad>): RosterPad => ({
  player: 1, name: 'PS4 Controller', kernelName: 'Wireless Controller', vendor: '054c', product: '09cc',
  connection: 'Bluetooth', battery: 85, charging: false, known: 'sdl', controls: null, analogTriggers: true, ...over,
})
const DS4 = 'Wireless Controller (STANDARD GAMEPAD Vendor: 054c Product: 09cc)'
const XBOX = 'Xbox Wireless Controller (STANDARD GAMEPAD Vendor: 045e Product: 0b13)'

describe('padLayout', () => {
  it('reads vendor and product out of a Linux gamepad id', () => {
    expect(vidPid(DS4)).toBe('054c:09cc')
    expect(vidPid('Some pad')).toBeNull()
  })

  it('pairs each browser pad with its roster row, identical pads in order', () => {
    const m = matchRoster([gp(1, DS4), gp(0, DS4)], [row({ player: 1 }), row({ player: 2 })])
    expect(m.get(0)?.player).toBe(1)
    expect(m.get(1)?.player).toBe(2)
  })

  it('draws every control for a standard pad with no SDL answer', () => {
    expect(presentControls(state(), undefined).size).toBe(19)
  })

  it('drops the sticks and their clicks for an arcade stick', () => {
    const has = presentControls(state(), row({ controls: ['south', 'east', 'west', 'north', 'l1', 'r1', 'l2', 'r2', 'home'] }))
    for (const c of ['ls', 'rs', 'l3', 'r3']) expect(has.has(c)).toBe(false)
    expect(missingSentence(has, false)).toBe('Not on this pad: left stick, right stick, Select. Triggers are buttons, not analog.')
  })

  it('marks Home absent when the browser reports only 16 buttons', () => {
    expect(presentControls(state({ pressed: Array(16).fill(false) }), undefined).has('home')).toBe(false)
  })

  it('names what is held by position, not by symbol', () => {
    const pressed = Array(17).fill(false); pressed[1] = true; pressed[3] = true
    expect(pressedControls(state({ pressed }))).toEqual({ east: true, north: true })
  })

  it('says plainly when a pad is raw or unknown', () => {
    const base = { index: 0, player: 1, name: 'x', connection: 'USB', battery: null, charging: false, active: true }
    expect(padStatus({ ...base, known: 'sdl', raw: true })?.tone).toBe('warn')
    expect(padStatus({ ...base, known: 'unknown', raw: false })?.text).toMatch(/^Not recognised/)
    expect(padStatus({ ...base, known: 'mapped', raw: false })?.tone).toBe('ok')
    expect(padStatus(null)).toBeNull()
  })

  it('lists two pads by player and marks the one being read', () => {
    const pads = buildPads([gp(0, XBOX), gp(1, DS4)],
      [row({ player: 1 }), row({ player: 2, vendor: '045e', product: '0b13', name: 'Xbox Wireless Controller' })], 1)
    expect(pads.map(p => [p.player, p.name, p.active])).toEqual([
      [1, 'PS4 Controller', true], [2, 'Xbox Wireless Controller', false]])
  })

  it('names a pad the backend has not seen from its browser id', () => {
    const [p] = buildPads([gp(0, 'USB Gamepad (Vendor: 0079 Product: 0006)', '')], [], 0)
    expect(p.name).toBe('USB Gamepad')
    expect(p.raw).toBe(true)
  })
})
