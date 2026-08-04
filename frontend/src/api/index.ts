const BASE = '/api'

export interface SystemEntry {
  id: string
  kind: 'emulator' | 'app'
  type?: string
  platform?: string
  label?: string
  color?: string
  iconPath?: string
  romsPath?: string
  extensions?: string[]
  path?: string
  args?: string
}

export interface GameEntry {
  filename: string
  display_name: string
  path: string
  size: number
  ext: string
}

export interface GameMeta {
  found: boolean
  title: string
  description: string
  year: string
  genres: string[]
  /** Highest player count the sources know: "1-3" arrives here as 3. */
  players: number
  /** Age rating (ESRB, PEGI as a fallback) — a label, not a score. */
  rating: string

  // ── Filled in by the gamemedia tier (ScreenScraper / LaunchBox) ──────────
  // All optional: a box with no ScreenScraper account and no LaunchBox index
  // answers from TheGamesDB, which has none of them. Read them with `?.`.
  source?: 'screenscraper' | 'launchbox' | ''
  developer?: string
  publisher?: string
  /** Full ISO date when known ("2011-05-10"); `year` is extracted from it. */
  released?: string
  /** The raw player string, "1-3" — `players` is the number. */
  players_label?: string
  /** Community score normalised to 0–1, ready to multiply by 5 stars. */
  score?: number | null
  /** Number of votes behind `score` (LaunchBox only). 5.0 from 2 votes is not 4.7 from 987. */
  score_count?: number | null
  /** { PEGI: "16", ESRB: "T", USK: "16", … } */
  classifications?: Record<string, string>
  platform?: string
}

/** One artwork a game has. The file itself is at `api.media.url(...)`. */
export interface MediaEntry {
  /** box, cart, logo, screenshot, mix, marquee, artwork, icon, bezel, video, document, theme, pinball */
  category: string
  kind: 'image' | 'video' | 'document' | 'archive'
  region: string
  /** Already on disk. False means the first request pays one download. */
  cached: boolean
}

export interface GameMediaIndex {
  found: boolean
  /** False = no media source configured on this box — not "game unknown". */
  available: boolean
  source?: string
  matched_by?: string
  meta: Partial<GameMeta>
  /** Keyed by media type: "box-3d", "clear-logo", "screenshot-gameplay", … */
  media: Record<string, MediaEntry>
  /** True = we could not ask (quota, network). Retrying later is worth something. */
  unreachable?: boolean
  notes?: string[]
}

/** One pack in the catalogue — an emulator or an application. */
export interface CatalogEntry {
  id: string
  kind: 'emulator' | 'app'
  label: string
  platform: string
  /** Who made the hardware — 'Nintendo', 'Sony'... Empty when the pack does not
   *  say, which groups it under "Other" rather than guessing from the id. */
  family: string
  color: string
  /** The product name when it differs from the platform label: the N64 slot is
   *  labelled "Nintendo 64" and runs "Rosalie's Mupen GUI". */
  emulatorName: string
  description: string
  /** 'shipped' with the release, or 'local' from config/catalog.d/. */
  origin: 'shipped' | 'local'
  /** Its tile is on the grid. Not "the application is present" — see api.catalog. */
  installed: boolean
  /** Blocks ignored because a local pack is data only (generator.py, services…). */
  restricted: string[]
}

export interface PlaytimeEntry {
  game_key: string
  system_id: string
  total_secs: number
  session_count: number
  last_played: string | null
}

export interface SysInfo {
  ip: string
  storage_used_gb: number
  storage_total_gb: number
  storage_free_gb: number
  version: string
  controllers: { level: number; name?: string; label?: string; player?: number | null; charging?: boolean }[]
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

export const api = {
  systems: {
    list: () => get<SystemEntry[]>('/systems'),
    get: (id: string) => get<SystemEntry>(`/systems/${encodeURIComponent(id)}`),
  },
  games: {
    list: (systemId: string) => get<GameEntry[]>(`/systems/${encodeURIComponent(systemId)}/games`),
    launch: (systemId: string, romPath = '', gameKey = '') =>
      post('/games/launch', { system_id: systemId, rom_path: romPath, game_key: gameKey }),
    kill: () => post('/games/kill'),
    session: () => get<{ game_key?: string; system_id?: string }>('/games/session'),
  },
  metadata: {
    get: (systemId: string, filename: string) =>
      get<GameMeta>(`/metadata/${encodeURIComponent(systemId)}/${encodeURIComponent(filename)}`),
  },
  /**
   * Every artwork a game has, not just its jacket.
   *
   * `list()` says what exists — that is the call to make first, because what a
   * game has depends on the game: a PS3 dump carries 28 media, an obscure
   * cartridge three. `url()` builds the src for one of them; it is a plain
   * string, so it goes straight into an <img> or a <video>.
   *
   * Nothing is downloaded before it is asked for, so the first display of a
   * type costs one round trip and every one after it is served from disk.
   */
  media: {
    list: (systemId: string, filename: string) =>
      get<GameMediaIndex>(`/media/${encodeURIComponent(systemId)}/${encodeURIComponent(filename)}`),
    url: (systemId: string, filename: string, type: string) =>
      `${BASE}/media/${encodeURIComponent(systemId)}/${encodeURIComponent(filename)}/media/${encodeURIComponent(type)}`,
  },
  playtime: {
    all: () => get<PlaytimeEntry[]>('/playtime'),
    forSystem: (id: string) => get<PlaytimeEntry[]>(`/playtime/system/${encodeURIComponent(id)}`),
    forGame: (key: string) => get<PlaytimeEntry>(`/playtime/game/${encodeURIComponent(key)}`),
  },
  /**
   * The pack catalogue: everything this box COULD run, and adding it without
   * re-running the installer.
   *
   * `installed` is about the grid — the tile the player sees. Whether the
   * Flatpak itself is present is a different question, and answering it needs
   * the network (`gamecore-emu verify`).
   *
   * install/remove/reconfigure return as soon as the CLI has started; progress
   * arrives on the WebSocket as `catalog:log`, and `catalog:done` closes it.
   */
  catalog: {
    list: () => get<CatalogEntry[]>('/catalog'),
    busy: () => get<{ busy: boolean }>('/catalog/busy'),
    install: (id: string) => post(`/catalog/${encodeURIComponent(id)}/install`),
    remove: (id: string) => post(`/catalog/${encodeURIComponent(id)}/remove`),
    reconfigure: (id: string) => post(`/catalog/${encodeURIComponent(id)}/reconfigure`),
  },
  standby: {
    get: () => get<{ state: string; enabled: boolean; screensaver_mins: number; sleep_mins: number }>('/standby'),
    setConfig: (cfg: { enabled?: boolean; screensaver_mins?: number; sleep_mins?: number }) =>
      post<{ ok: boolean; enabled: boolean; screensaver_mins: number; sleep_mins: number }>('/standby/config', cfg),
    exit: () => post('/standby/exit'),
  },
  sysinfo: () => get<SysInfo>('/sysinfo'),
  update: {
    check: () => get<{ update_available: boolean; current: string; latest: string; download_url?: string }>('/update/check'),
    apply: () => post('/update/apply'),
    // The backend is the source of truth for "is an update running": component
    // state does not survive leaving the page, and an update outlives that.
    status: () => get<{ running: boolean }>('/update/status'),
  },
  wifi: {
    networks: () => get<{ ssid: string; signal: number; secured: boolean; connected: boolean }[]>('/settings/wifi/networks'),
    status: () => get<{ connected: boolean; ssid: string; ip: string; iface: string; ethernet: { connected: boolean; iface: string; ip: string } }>('/settings/wifi/status'),
    connect: (ssid: string, password = '') => post<{ ok: boolean; wrong_password: boolean; error?: string }>('/settings/wifi/connect', { ssid, password }),
    disconnect: () => fetch(BASE + '/settings/wifi/connect', { method: 'DELETE' }).then(r => r.json()) as Promise<{ ok: boolean; error?: string }>,
  },
  audio: {
    get: () => get<{ volume: number; muted: boolean }>('/settings/audio'),
    sinks: () => get<{ id: string; name: string; default: boolean }[]>('/settings/audio/sinks'),
    setVolume: (volume: number) => post('/settings/audio/volume', { volume }),
    setSink: (sink: string) => post('/settings/audio/sink', { sink }),
  },
  bluetooth: {
    devices: () => get<{ mac: string; name: string; connected: boolean }[]>('/settings/bluetooth/devices'),
    scan: () => post('/settings/bluetooth/scan'),
    connect: (mac: string) => post<{ ok: boolean; message: string }>('/settings/bluetooth/connect', { mac }),
    disconnect: (mac: string) => post<{ ok: boolean }>('/settings/bluetooth/disconnect', { mac }),
    remove: (mac: string) => fetch(`/api/settings/bluetooth/devices/${encodeURIComponent(mac)}`, { method: 'DELETE' }).then(r => r.json()) as Promise<{ ok: boolean }>,
  },
}
