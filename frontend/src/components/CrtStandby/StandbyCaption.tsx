import { useEffect, useState } from 'react'
import type { StandbyItem } from '../../api/standby'
import { captionMeta } from '../../lib/standbyPlaylist'

const clockOf = (d: Date) => d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
const dateOf = (d: Date) => d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })

/** What is on the TV, when it was last played, and the time. */
export function StandbyCaption({ item }: { item: StandbyItem | null }) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 10_000)
    return () => clearInterval(t)
  }, [])
  return (
    <div className="crt-caption">
      {item && <>
        <p className="crt-caption-label">Now on the TV</p>
        <p className="crt-caption-title">{item.display_name}</p>
        <p className="crt-caption-meta">{captionMeta(item, now)}</p>
      </>}
      <div className="crt-caption-time">
        <span className="crt-caption-clock">{clockOf(now)}</span>
        <span className="crt-caption-date">{dateOf(now)}</span>
      </div>
      <p className="crt-caption-hint">Press any button to wake</p>
    </div>
  )
}
