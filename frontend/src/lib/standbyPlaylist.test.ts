import { describe, it, expect } from 'vitest'
import { captionMeta, clipSeconds, CLIP_MAX_S, nextIndex, playedAgo, reelItems, reelMode } from './standbyPlaylist'
import type { StandbyItem } from '../api/standby'

const item = (over: Partial<StandbyItem> = {}): StandbyItem => ({
  system_id: 'snes9x', filename: 'Chrono Trigger (USA).sfc', display_name: 'Chrono Trigger',
  system_name: 'Super Nintendo', last_played: null, media_type: 'video-normalized',
  url: '/api/media/snes9x/x/media/video-normalized', ...over,
})

describe('standby playlist', () => {
  it('plays videos first, screenshots when there are none, else no signal', () => {
    const v = [item()], s = [item({ media_type: 'screenshot-gameplay' })]
    expect(reelMode({ videos: v, stills: s })).toBe('video')
    expect(reelMode({ videos: [], stills: s })).toBe('still')
    expect(reelMode({ videos: [], stills: [] })).toBe('none')
    expect(reelMode(null)).toBe('none')
    expect(reelItems({ videos: v, stills: s }, 'still')).toBe(s)
    expect(reelItems(null, 'video')).toEqual([])
  })

  it('plays a clip for its length or the cap, whichever is shorter', () => {
    expect(clipSeconds(12)).toBe(12)
    expect(clipSeconds(90)).toBe(CLIP_MAX_S)
    expect(clipSeconds(NaN)).toBe(CLIP_MAX_S)
    expect(clipSeconds(Infinity)).toBe(CLIP_MAX_S)
  })

  it('wraps around, and a list of one replays itself', () => {
    expect(nextIndex(0, 3)).toBe(1)
    expect(nextIndex(2, 3)).toBe(0)
    expect(nextIndex(0, 1)).toBe(0)
    expect(nextIndex(0, 0)).toBe(0)
  })

  it('says when the game was last played, in calendar days', () => {
    const now = new Date(2026, 9, 10, 9, 0)
    expect(playedAgo(null, now)).toBeNull()
    expect(playedAgo('garbage', now)).toBeNull()
    expect(playedAgo('2026-10-10T08:00:00', now)).toBe('played today')
    expect(playedAgo('2026-10-09T23:30:00', now)).toBe('played yesterday')
    expect(playedAgo('2026-10-07T20:00:00', now)).toBe('played 3 days ago')
    expect(playedAgo('2026-09-12T20:00:00', now)).toBe('played 4 weeks ago')
    expect(playedAgo('2025-10-01T20:00:00', now)).toBe('played 12 months ago')
  })

  it('writes the caption line without separators', () => {
    const now = new Date(2026, 9, 10)
    expect(captionMeta(item(), now)).toBe('Super Nintendo')
    expect(captionMeta(item({ last_played: '2026-10-07T20:00:00' }), now))
      .toBe('Super Nintendo, played 3 days ago')
  })
})
