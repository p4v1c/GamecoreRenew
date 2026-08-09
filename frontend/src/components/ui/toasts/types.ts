/**
 * What a toast stack is handed, and all it is allowed to do.
 *
 * Same seam as the dashboard and the library: which events become a toast, how
 * long each one stays, which ones go to the Electron HUD instead, and the
 * click-through rule all live in `useToastQueue` — for the default and themed
 * alike. A view only draws.
 *
 * The line matters more here than it looks. A toast is the only part of the UI
 * that appears without the player asking, and every one of them is load-bearing:
 * a ROM finished uploading, a pad connected, a pad is unrecognised and here is
 * the offer to fix it, the game you just launched did not start. Before this,
 * `Toasts` was rendered by `DefaultShell` and was not one of the parts, so a
 * shell that redrew everything lost all of them — silently, and only on the
 * machine of whoever was standing in front of the TV.
 */
export interface Toast {
  id: number
  icon: string
  title: string
  body: string
  accent: string
  /** An offer the player can take, drawn as a button inside the toast. */
  action?: { label: string; run: () => void }
}

export interface ToastsViewProps {
  /** Live, in the order they arrived. The host removes each one on its own timer. */
  toasts: Toast[]
  /**
   * Take one down early. The host still owns the timers — this only brings a
   * dismissal forward, it cannot extend one.
   *
   * A view that draws `action` must call this after running it, or the offer
   * stays on screen having already been taken.
   */
  onDismiss: (id: number) => void
}
