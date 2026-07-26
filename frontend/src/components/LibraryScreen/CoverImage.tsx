import { useState } from 'react'
import { hexToRgb } from '../ui'

/** Cover art, with the missing-art fallback the covers API needs. */
export default function CoverImage({ filename, systemId, color }: {
  filename: string; systemId: string; color: string
}) {
  const src = `/api/covers/${systemId}/${encodeURIComponent(filename)}`
  const [errored, setErrored] = useState(false)
  const rgb = hexToRgb(color)

  if (errored) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, padding: 16 }}>
        <div style={{ width: 48, height: 48, borderRadius: 12, background: `rgba(${rgb},0.3)`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24 }}>🎮</div>
        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', textAlign: 'center', wordBreak: 'break-all' }}>
          {filename.slice(0, 30)}
        </div>
      </div>
    )
  }

  return (
    <img
      src={src}
      alt={filename}
      onError={() => setErrored(true)}
      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
    />
  )
}
