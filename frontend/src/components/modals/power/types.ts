export interface PowerOption {
  id: string
  label: string
  /** Shown in place of the label while this option is running. */
  busy: string
  icon: string
  color: string
  desc: string
}

/**
 * What a power menu is handed, and all it is allowed to do.
 *
 * The flow stays in PowerModal: the two-press confirmation, the pending lock
 * that keeps every close path inert, the failsafe that unfreezes the UI when
 * the OS never actually powers off, and the mapping scan. A view that could
 * reimplement those could also get shutdown wrong.
 */
export interface PowerViewProps {
  options: PowerOption[]
  focusIdx: number
  /** The option awaiting its second press, if any. */
  confirmId: string | null
  /** A power command is in flight: the screen must stay up and refuse input. */
  pendingId: string | null
  scanning: boolean
  /** Outcome of the last mapping scan, already formatted. */
  scanResult: string | null
  onFocus: (idx: number) => void
  onActivate: (id: string) => void
  /** Cancel. Already inert while a power command is in flight. */
  onCancel: () => void
}
