interface OverlayData {
  system_id: string
  rect?: { x: number; y: number; w: number; h: number }
  /** The bezel this launch resolved to, already URL-encoded, or null when
   *  none was found. Absent means an older main process: the overlay falls
   *  back to the per-system path it used to build itself. */
  asset?: string | null
  /** Which level of the cascade answered — 'game' | 'system' | 'declared'. */
  source?: string
}

interface GamecoreAPI {
  reboot:   () => void
  shutdown: () => void
  quit:     () => void

  overlayStart: (system_id: string, game_key?: string) => void
  overlayStop:  (system_id: string) => void

  batteryToast:    (data: { level: number; player?: number | null }) => void
  /**
   * `unconfigured` is systems the pipeline gave up on — a fault. `autoconfigOff`
   * is systems it was told not to touch — a setting. The HUD draws different
   * sentences for them and only ever receives one, because a pad that got
   * nothing because of the switch has no give-ups to report.
   */
  controllerToast: (data: { player?: number | null; label?: string; connected: boolean; unconfigured?: string[]; autoconfigOff?: string[] }) => void

  onOverlayShow:    (cb: (data: OverlayData) => void) => void
  onOverlayHide:    (cb: (data: OverlayData) => void) => void
  onOverlayWaiting: (cb: (data: OverlayData) => void) => void
}

declare global {
  interface Window {
    gamecore?: GamecoreAPI
  }
}

export {}
