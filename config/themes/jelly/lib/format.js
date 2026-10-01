/** Playtime and "last played", in French.
 *
 * Same thresholds as the host's `sdk.format.time` / `date` (components/ui),
 * which speak English; only the words change, so Jelly never disagrees with
 * the rest of the box about how long or how recently. */
export function duration(secs) {
  if (!secs || secs <= 0) return 'Jamais joué'
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (h > 0 && m > 0) return `${h} h ${String(m).padStart(2, '0')}`
  if (h > 0) return `${h} h`
  return `${m} min`
}

export function lastPlayed(iso) {
  if (!iso) return 'Jamais joué'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const days = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (days <= 0) return 'Aujourd’hui'
  if (days === 1) return 'Hier'
  if (days < 7) return `Il y a ${days} jours`
  return d.toLocaleDateString('fr-FR', {day: 'numeric', month: 'short'})
}
