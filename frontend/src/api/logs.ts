/** Settings → System → Purge logs. The whole logs directory, never one section. */
export interface LogsUsage { files: number; bytes: number }

export const logs = {
  usage: (): Promise<LogsUsage> => fetch('/api/logs').then((r) => r.json()),
  purge: async (): Promise<{ ok: boolean; freed: LogsUsage }> => {
    const r = await fetch('/api/logs', { method: 'DELETE' })
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
    return r.json()
  },
}
