/** Who plays on this box (Settings → Profiles, the "Who's playing?" screen). */
import { get, sendDetailed } from './http'

export interface Profile {
  id: string
  name: string
  color: string
  /** A built-in avatar key; null draws the initial on `color`. */
  avatar: string | null
  created: string
  primary: boolean
}

export interface ProfilesState { active: string; profiles: Profile[]; palette: { color: string; name: string }[] }

export type ProfileFields = Partial<Pick<Profile, 'name' | 'color' | 'avatar'>>

// Errors carry the backend's sentence ("Sam is already a profile.").
export const profiles = {
  list: () => get<ProfilesState>('/profiles'),
  create: (fields: ProfileFields & { name: string }) => sendDetailed<Profile>('POST', '/profiles', fields),
  update: (id: string, fields: ProfileFields) =>
    sendDetailed<Profile>('PATCH', `/profiles/${encodeURIComponent(id)}`, fields),
  remove: (id: string) => sendDetailed<{ active: string }>('DELETE', `/profiles/${encodeURIComponent(id)}`),
  setActive: (id: string) => sendDetailed<Profile>('PUT', '/profiles/active', { id }),
}
