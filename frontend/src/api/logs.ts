/** The logs directory: its size and purge (Settings → System), and UI error reports. */
import { get, del, post } from './http'

export interface LogsUsage { files: number; bytes: number }

export const logs = {
  usage: () => get<LogsUsage>('/logs'),
  purge: () => del<{ ok: boolean; freed: LogsUsage }>('/logs'),
  /** An error the interface caught, into logs/ui. */
  ui: (message: string, source = '') => post<{ ok: boolean }>('/logs/ui', { message, source }),
}
