/** The logs directory: its size and purge (Settings → System), and UI error reports. */
export interface LogsUsage { files: number; bytes: number }

export const logs = {
  usage: (): Promise<LogsUsage> => fetch('/api/logs').then((r) => r.json()),
  purge: async (): Promise<{ ok: boolean; freed: LogsUsage }> => {
    const r = await fetch('/api/logs', { method: 'DELETE' })
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
    return r.json()
  },
  /** An error the interface caught, into logs/ui. Fire and forget. */
  ui: (message: string, source = ''): Promise<unknown> =>
    fetch('/api/logs/ui', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, source }),
    }),
}
