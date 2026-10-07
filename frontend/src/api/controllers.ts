/** Controller types: the roster, peripherals, autoconfig and the mapping wizard. */

/** One connected pad as the backend knows it — see api.controllers.pads. */
export interface RosterPad {
  /** What a profile keeps it by: the MAC, else vendor:product. */
  id: string
  player: number | null
  /** For a human: SDL3's name, else the community DB's, else the kernel's. */
  name: string
  kernelName: string
  vendor: string
  product: string
  connection: 'USB' | 'Bluetooth' | 'Wired'
  battery: number | null
  charging: boolean
  /** mapped: the owner's wizard capture; sdl/table: SDL3 names it; unknown: it does not. */
  known: 'mapped' | 'sdl' | 'table' | 'unknown'
  /** Standard controls its SDL mapping binds; null when SDL has no mapping. */
  controls: string[] | null
  analogTriggers: boolean
}

/** One declared peripheral that is not an SDL pad — see api.controllers.devices. */
export interface UsbDevice {
  system_id: string
  system_label: string
  vid_pid: string
  /** 'gamepad' | 'adapter' | 'wheel' | 'lightgun' | 'arcade', or 'unknown' for
   *  a class this release does not know — a pack from a newer catalogue. */
  class: string
  label: string
  /** The pack's own words about what to check. Shown when the device is absent. */
  note: string
  /** What sysfs calls it, when it is here. Empty when absent. */
  detected_as: string
  status: 'present' | 'absent'
}

/** One emulator's row on the autoconfig screen. */
export interface AutoconfigPack {
  id: string
  /** The system as a player names it — "GameCube / Wii", not "dolphin". */
  label: string
  /** Its own exception, which is what its row shows and what it sets. */
  enabled: boolean
  /**
   * What is actually in force: `enabled` AND the global switch.
   *
   * The two differ exactly when the global switch is off, and that gap is the
   * reason this field is sent rather than recomputed in the UI — a screen
   * showing rows that read "on" for emulators that are not running is the
   * failure this whole feature is trying not to become.
   */
  effective: boolean
  /**
   * Whether this emulator has an inverse at all.
   *
   * Four of the ten do not — they bind by GUID and raw indices, so nothing
   * frees them when a pad leaves either. Switching autoconfig off for one of
   * those empties nothing, and the confirmation has to say so rather than
   * promise a clear-out that cannot happen.
   */
  releasable?: boolean
}

export interface AutoconfigState {
  ok: boolean
  enabled: boolean
  packs: AutoconfigPack[]
}

/** One step of the wizard: an SDL field name, and what to ask the player for. */
export interface MappingStep {
  field: string
  kind: 'button' | 'axis'
  label: string
}

export interface MappingSession {
  ok: boolean
  session?: string
  controller?: string
  vendor?: string
  product?: string
  /** One per SDL identity the pad has — see controller_capture.sdl_guids. */
  guids?: string[]
  nodes?: string[]
  steps?: MappingStep[]
  /** Fields a pad may legitimately lack, so a gap is not an abandoned capture. */
  optional?: string[]
  error?: string
}

export interface MappingCommit {
  ok: boolean
  controller?: string
  lines?: string[]
  bindings?: number
  /** Required fields left unbound — empty means the capture is complete. */
  missing?: string[]
  database?: string
  error?: string
}

export interface SavedMapping {
  guid: string
  name: string
  line: string
}
