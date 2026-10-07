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
  /** The theme put on when this profile plays: an id, or null for the
   *  built-in look. Absent until the profile has worn one. */
  theme?: string | null
  /** Pads shown on the profile's page, for display only; absent = none. */
  controllers?: ProfileController[]
}

/** `id` matches `RosterPad.id`; `name` is shown while the pad is off. */
export interface ProfileController {
  id: string
  name: string
}

export interface ProfilesState {
  active: string
  /** Start as the active profile without asking who is playing. */
  auto_login?: boolean
  profiles: Profile[]
  palette: { color: string; name: string }[]
  /** Labels of the systems whose saves follow the profile playing. */
  separate_saves: string[]
  /** Labels of the emulators whose saves every profile shares. */
  shared_saves?: string[]
}

export type ProfileFields = Partial<Pick<Profile, 'name' | 'color' | 'avatar' | 'theme'>>

// Errors carry the backend's sentence ("Sam is already a profile.").
export const profiles = {
  list: () => get<ProfilesState>('/profiles'),
  create: (fields: ProfileFields & { name: string }) => sendDetailed<Profile>('POST', '/profiles', fields),
  update: (id: string, fields: ProfileFields) =>
    sendDetailed<Profile>('PATCH', `/profiles/${encodeURIComponent(id)}`, fields),
  remove: (id: string) => sendDetailed<{ active: string }>('DELETE', `/profiles/${encodeURIComponent(id)}`),
  setActive: (id: string) => sendDetailed<Profile>('PUT', '/profiles/active', { id }),
  addController: (id: string, controllerId: string) =>
    sendDetailed<Profile>('POST', `/profiles/${encodeURIComponent(id)}/controllers`, { id: controllerId }),
  removeController: (id: string, controllerId: string) =>
    sendDetailed<Profile>('DELETE',
      `/profiles/${encodeURIComponent(id)}/controllers/${encodeURIComponent(controllerId)}`),
  setAutoLogin: (enabled: boolean) =>
    sendDetailed<{ auto_login: boolean }>('PUT', '/profiles/auto-login', { enabled }),
}
