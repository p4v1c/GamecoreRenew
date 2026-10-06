import { api } from '../api'

/**
 * Errors the interface hits, into `logs/ui/ui.log` (POST /api/logs/ui).
 * Capped per page load: a render loop that throws must not flood the backend.
 */
export const MAX_REPORTS = 50
const MESSAGE_MAX = 2000
const SOURCE_MAX = 300
let sent = 0

export function reportError(message: string, source = ''): void {
  if (sent >= MAX_REPORTS) return
  sent += 1
  api.logs.ui(message.slice(0, MESSAGE_MAX), source.slice(0, SOURCE_MAX)).catch(() => {})
}

/** Uncaught errors and rejected promises. Render errors come from ErrorBoundary. */
export function installErrorReports(target: Window = window): void {
  target.addEventListener('error', (e: ErrorEvent) =>
    reportError(String(e.message || e.error), e.filename ? `${e.filename}:${e.lineno}` : ''))
  target.addEventListener('unhandledrejection', (e: PromiseRejectionEvent) => {
    const reason = e.reason instanceof Error ? e.reason.message : String(e.reason)
    reportError(`Unhandled rejection: ${reason}`)
  })
}

/** Tests only: start a fresh page load's budget. */
export function resetReports(): void { sent = 0 }
