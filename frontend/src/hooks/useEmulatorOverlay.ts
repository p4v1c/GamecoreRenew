import { useEffect } from 'react'
import { useStore } from '../store'
import { syncSession } from './useWebSocket'

/**
 * The bezel window, kept in step with the session that is actually on screen.
 *
 * It used to be driven straight off `game:started` and `game:finished`, which
 * was correct while a session could only start or end. Suspending broke it in
 * the worst possible way: `overlay:stop` is what tears the bezel down **and
 * brings Electron's main window back** — `window:ready` hides `mainWindow` when
 * the overlay starts — so a suspend that never sent it left the player looking
 * at a frozen bezel with the interface hidden behind it. The controller worked;
 * there was nothing on screen to point it at.
 *
 * So the overlay follows the reconciled foreground rather than raw events.
 * `sessionGameKey` already means "a game owns the screen" and already goes null
 * on suspend, so one subscription covers start, suspend, resume, swap and end —
 * and cannot drift from the input guard, because it is the same value.
 */
export function useEmulatorOverlay(): void {
  useEffect(() => {
    // What the overlay is currently showing, as opposed to what the store says
    // it should be. Kept locally: `overlayStart` is not idempotent — it takes a
    // run number in main.js — so it must be called on change, not on render.
    let shown: { key: string; system: string } | null = null

    const sync = () => {
      const s = useStore.getState()
      const next = s.sessionGameKey && s.sessionSystemId
        ? { key: s.sessionGameKey, system: s.sessionSystemId }
        : null
      if (shown?.key === next?.key && shown?.system === next?.system) return
      // Stop the old one before starting the new: a swap moves both slots at
      // once, and two live overlays is a bezel for a game nobody is playing.
      if (shown) window.gamecore?.overlayStop(shown.system)
      shown = next
      // `game_key` is the ROM filename the launcher recorded, and it is what
      // picks this game's bezel out of a pack. Passing only system_id gets the
      // system bezel for every game, which is the feature not existing.
      if (next) window.gamecore?.overlayStart(next.system, next.key)
    }

    sync()
    const off = useStore.subscribe(sync)

    // Electron's own signal, for the case where the websocket is slow or a
    // message was missed. It used to clear the session outright — but a hidden
    // window is not evidence that a process exited, and with suspending it
    // frequently is not: the box is asked instead.
    window.gamecore?.onOverlayHide(() => { void syncSession() })

    return off
  }, [])
}
