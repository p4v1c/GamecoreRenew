import * as React from 'react'
import { cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

const load = (file: string) => import(/* @vite-ignore */ `../../../config/themes/orbit/${file}.js`)
afterEach(cleanup)
const systems = [
  { id: 'rpcs3', kind: 'emulator', label: 'RPCS3' },
  { id: 'youtube', kind: 'app', label: 'YouTube', platform: 'Web' },
  { id: 'twitch', type: 'application', label: 'Twitch', platform: 'Media' },
]
const games = Array.from({ length: 8 }, (_, i) => ({ filename: `Game ${i}.iso`, display_name: `Game ${i}`, path: `/test/${i}.iso` }))
const history = games.map((g, i) => ({ system_id: 'rpcs3', game_key: g.filename,
  last_played: `2026-09-${String(20 - i).padStart(2, '0')}T12:00:00Z`, total_secs: 100 }))

async function recent(entries: unknown[]) {
  const { createHomeHooks } = await load('views/home/hooks')
  const list = vi.fn(async (_id: string) => games)
  const sdk = { ui: React, api: { playtime: { all: async () => entries }, games: { list } },
    format: { gameName: (s: string) => s } }
  const { useRecent } = createHomeHooks(sdk, {}, {})
  const hook = renderHook(() => useRecent(systems))
  await waitFor(() => expect(hook.result.current).toHaveLength(6))
  return { rows: hook.result.current as { kind: string; systemId: string; gameKey: string; title: string }[], list }
}

it('does not reserve home slots for unused apps when six games were used more recently', async () => {
  const { rows, list } = await recent(history)
  expect(rows.map(r => r.title)).toEqual(['Game 0', 'Game 1', 'Game 2', 'Game 3', 'Game 4', 'Game 5'])
  expect(list.mock.calls).toEqual([['rpcs3']])
})

it('ranks apps by actual usage among games within the same six slots', async () => {
  const { rows } = await recent([...history,
    { system_id: 'youtube', game_key: 'youtube', last_played: '2026-09-21T12:00:00Z', total_secs: 30 },
    { system_id: 'twitch', game_key: 'twitch', last_played: '2026-09-19T18:00:00Z', total_secs: 300 },
    { system_id: 'removed-app', game_key: 'removed-app', last_played: '2026-09-22T12:00:00Z' },
  ])
  expect(rows.map(r => r.title)).toEqual(['YouTube', 'Game 0', 'Twitch', 'Game 1', 'Game 2', 'Game 3'])
  expect(rows[0]).toMatchObject({ kind: 'app', systemId: 'youtube', gameKey: 'youtube' })
  expect(rows[1]).toMatchObject({ kind: 'game', systemId: 'rpcs3', gameKey: 'Game 0.iso' })
})

it('uses app labels rather than their platform without renaming consoles', async () => {
  const { systemName } = await load('lib/catalog')
  expect(systemName(systems[1])).toBe('YouTube')
  expect(systemName(systems[2])).toBe('Twitch')
  expect(systemName({ id: 'other', type: 'app', platform: 'Web' })).toBe('other')
  expect(systemName({ id: 'rpcs3', kind: 'emulator', label: 'RPCS3', platform: 'PlayStation 3' })).toBe('PlayStation 3')
})
