/** A pad linked to a profile is shown by that profile's name, whichever
 *  profile is active; any other pad, player 1 included, is P<n>. */
import { createElement } from 'react'
import { render, waitFor, cleanup } from '@testing-library/react'
import { it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { Profile, RosterPad } from '../api'
import { buildSdk } from './themeSdk'
import { controllerTitle, padOwners, playerLabel, playerTitle, refreshPlayers } from './players'
import { useStore } from '../store'

const SUMMER = '../../../config/themes/summer'
const DS4 = '84:30:95:07:c8:1c'
const pad = (id: string, player: number) => ({ id, player, vendor: '054c', product: '09cc' }) as RosterPad
const profile = (id: string, name: string, controllers: string[] = []) =>
  ({ id, name, color: '#127a6d', avatar: null, created: '', primary: id === 'a',
     controllers: controllers.map((c) => ({ id: c, name: 'PS4 Controller' })) }) as Profile

let state: { active: string; profiles: Profile[] }
let roster: RosterPad[]
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const body = String(url).endsWith('/controllers/pads') ? { pads: roster }
      : String(url).endsWith('/sysinfo') ? { controllers: roster.map((p) => ({ player: p.player, level: 80 })) }
        : { ...state, palette: [] }
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
})
afterEach(() => {
  cleanup(); vi.unstubAllGlobals()
  useStore.getState().setActiveProfile('', ''); useStore.getState().setPads([], {})
})

it('names a pad after the profile it is linked to, and nothing else', () => {
  const owners = padOwners([pad(DS4, 1), pad('045e:0b13', 2)],
    [profile('a', 'louis'), profile('b', 'jimmy', [DS4])])
  expect(owners).toEqual({ 1: 'jimmy' })
  expect(playerLabel(1, owners)).toBe('jimmy')
  expect(playerTitle(1, owners)).toBe('jimmy')
  expect(controllerTitle(1, owners)).toBe('jimmy’s controller')
  expect(playerLabel(2, owners)).toBe('P2')
  expect(playerTitle(2, owners)).toBe('Player 2')
  expect(controllerTitle(2, owners)).toBe('Controller 2')
  expect(controllerTitle(null, owners)).toBe('Controller')
})

it('names two pads after two profiles', () => {
  const owners = padOwners([pad(DS4, 1), pad('045e:0b13', 2)],
    [profile('a', 'louis', ['045e:0b13']), profile('b', 'jimmy', [DS4])])
  expect(owners).toEqual({ 1: 'jimmy', 2: 'louis' })
})

it('keeps a linked pad on its profile across a switch, and an unlinked P1 numbered', async () => {
  roster = [pad(DS4, 1)]
  state = { active: 'b', profiles: [profile('a', 'louis'), profile('b', 'jimmy', [DS4])] }
  await refreshPlayers()
  expect(useStore.getState().padOwners).toEqual({ 1: 'jimmy' })

  state = { ...state, active: 'a' }
  await refreshPlayers()
  expect(useStore.getState().profileName).toBe('louis')
  expect(playerLabel(1, useStore.getState().padOwners)).toBe('jimmy')

  state = { active: 'a', profiles: [profile('a', 'louis'), profile('b', 'jimmy')] }
  await refreshPlayers()
  expect(playerLabel(1, useStore.getState().padOwners)).toBe('P1')
})

it('leaves a box without profiles on P1 to P4', async () => {
  roster = [pad(DS4, 1), pad('045e:0b13', 2)]
  state = { active: 'a', profiles: [profile('a', '')] }
  await refreshPlayers()
  expect(useStore.getState().profileName).toBe('')
  expect(useStore.getState().padOwners).toEqual({})
  expect(controllerTitle(1, {})).toBe('Controller 1')
})

it('keeps the newest read when two land out of order', async () => {
  roster = [pad(DS4, 1)]
  state = { active: 'a', profiles: [profile('a', 'louis', [DS4])] }
  const first = refreshPlayers()
  state = { active: 'a', profiles: [profile('a', 'louis')] }
  await Promise.all([first, refreshPlayers()])
  expect(useStore.getState().padOwners).toEqual({})
})

it('gives themes the labels through sdk.players, status bar included', async () => {
  roster = [pad(DS4, 1), pad('045e:0b13', 2)]
  state = { active: 'a', profiles: [profile('a', 'louis'), profile('b', 'jimmy', [DS4])] }
  await refreshPlayers()
  const sdk = buildSdk('summer', { selectTheme: async () => {} })
  expect(sdk.players.label(1)).toBe('jimmy')
  expect(sdk.players.label(2)).toBe('P2')
  const { createTopBar } = await import(/* @vite-ignore */ `${SUMMER}/views/topbar.js`)
  const { container } = render(createElement(createTopBar(sdk), { onSettings: () => {}, onPower: () => {} }))
  await waitFor(() => expect([...container.querySelectorAll('.sm-pad-n')].map((n) => n.textContent))
    .toEqual(['jimmy', 'P2']))
})
