import { get } from './http'

/** One game the standby TV can show — see `GET /api/standby/videos`. */
export interface StandbyItem {
  system_id: string
  filename: string
  display_name: string
  /** The console's label, "Super Nintendo". */
  system_name: string
  /** Local ISO timestamp from the playtime table, null if never played. */
  last_played: string | null
  /** `video-normalized`, `video`, `screenshot-gameplay`… */
  media_type: string
  /** Same-origin file URL (`/api/media/.../media/<type>`), already on disk. */
  url: string
}

/** Clips on disk, and screenshots of the games without one. */
export interface StandbyPlaylist {
  videos: StandbyItem[]
  stills: StandbyItem[]
}

/** `favourites`: `system_id:filename` keys a theme keeps; they come up more often. */
export const standbyVideos = (favourites: string[] = []) => {
  const q = favourites.map(f => `favourite=${encodeURIComponent(f)}`).join('&')
  return get<StandbyPlaylist>(`/standby/videos${q ? `?${q}` : ''}`)
}
