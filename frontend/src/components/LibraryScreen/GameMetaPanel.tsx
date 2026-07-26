import { useState, useEffect } from 'react'
import { api, GameMeta } from '../../api'
import { Chip } from '../ui'

/** Year, genres, players and blurb. A 404 just means we know nothing — the
 *  extension chip still shows, so the row never renders empty. */
export default function GameMetaPanel({ systemId, filename, extChip, color }: {
  systemId: string; filename: string; extChip: React.ReactNode; color: string
}) {
  const [meta, setMeta] = useState<GameMeta | null>(null)

  useEffect(() => {
    let cancelled = false
    setMeta(null)
    api.metadata.get(systemId, filename)
      .then(m => { if (!cancelled) setMeta(m) })
      .catch(() => {})  // 404 = no metadata (no key / unknown game)
    return () => { cancelled = true }
  }, [systemId, filename])

  return (
    <>
      <div style={{ display: 'flex', gap: 8, marginBottom: meta?.description ? 14 : 24, flexWrap: 'wrap' }}>
        {extChip}
        {meta?.year && <Chip label={meta.year} color={color} />}
        {meta?.genres.slice(0, 3).map(g => <Chip key={g} label={g} color={color} />)}
        {(meta?.players ?? 0) > 1 && <Chip label={`${meta!.players} players`} color={color} />}
      </div>
      {meta?.description && (
        <p style={{
          fontSize: 13.5, lineHeight: 1.55, color: 'rgba(255,255,255,0.55)',
          maxWidth: 640, marginBottom: 24,
          display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>
          {meta.description}
        </p>
      )}
    </>
  )
}
