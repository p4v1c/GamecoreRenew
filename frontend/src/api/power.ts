import { get, postDetailed } from './http'

/** `resumes` grows by one per wake; see backend/services/resume.py. */
export interface PowerState {
  resting: boolean
  resumes: number
}

export const power = {
  /** Closes every game and app, then suspends. Throws the backend's sentence. */
  rest: () => postDetailed<{ ok: boolean; forced: number }>('/power/rest'),
  state: () => get<PowerState>('/power/state'),
}
