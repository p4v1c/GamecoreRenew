interface OverlayData {
  system_id: string
  rect?: { x: number; y: number; w: number; h: number }
}

interface GamecoreAPI {
  reboot:   () => void
  shutdown: () => void
  quit:     () => void

  overlayStart: (system_id: string) => void
  overlayStop:  (system_id: string) => void

  batteryToast:    (data: { level: number; player?: number | null }) => void
  controllerToast: (data: { player?: number | null; label?: string; connected: boolean }) => void

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
