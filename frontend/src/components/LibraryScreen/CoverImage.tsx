import { useState, useEffect } from 'react'
import { api } from '../../api'
import { hexToRgb } from '../ui'

/**
 * Cover art, with the missing-art fallback the covers API needs.
 *
 * `type` is the seam a theme uses to draw something other than a jacket:
 * `type="box-3d"` for the box in perspective, `"clear-logo"` for the cut-out
 * logo, `"screenshot-gameplay"`, `"mix-rbv2"`, … `api.media.list()` says what a
 * given game actually has.
 *
 * **Omitting it is the default and hits the exact same URL as before** —
 * /api/covers — so the default theme, Summer, and the screensaver keep the
 * pipeline they have always used, cache included.
 *
 * When a type is asked for and the game does not have it, the plain cover is
 * drawn instead. A theme built on 3D boxes would otherwise show a hole for
 * every game whose box was never photographed in perspective, and there are
 * plenty: it is a rarer artwork than the flat scan.
 */
export default function CoverImage({ filename, systemId, color, type }: {
  filename: string; systemId: string; color: string; type?: string
}) {
  const cover = `/api/covers/${systemId}/${encodeURIComponent(filename)}`
  const wanted = type ? api.media.url(systemId, filename, type) : cover

  const [src, setSrc] = useState(wanted)
  const [errored, setErrored] = useState(false)
  const rgb = hexToRgb(color)

  // Start over when the game or the requested type changes — without this the
  // panel would keep showing the previous game's fallback.
  useEffect(() => {
    setSrc(wanted)
    setErrored(false)
  }, [wanted])

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
      onError={() => (src !== cover ? setSrc(cover) : setErrored(true))}
      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
    />
  )
}
