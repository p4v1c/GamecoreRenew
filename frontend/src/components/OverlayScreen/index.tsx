import { useEffect, useState } from 'react'

interface OverlayData {
  system_id: string
  rect?: { x: number; y: number; w: number; h: number }
}

type Status = 'hidden' | 'waiting' | 'visible'

export default function OverlayScreen() {
  const [status, setStatus]   = useState<Status>('hidden')
  const [data, setData]       = useState<OverlayData | null>(null)
  const [imgOk, setImgOk]     = useState(false)

  useEffect(() => {
    if (!window.gamecore) return

    window.gamecore.onOverlayShow((d: OverlayData) => {
      setData(d)
      setImgOk(false)
      setStatus('visible')
    })
    window.gamecore.onOverlayWaiting((d: OverlayData) => {
      setData(d)
      setStatus('waiting')
    })
    window.gamecore.onOverlayHide(() => {
      setStatus('hidden')
      setData(null)
    })
  }, [])

  if (status === 'hidden') return null

  // Waiting spinner — emulator launching
  if (status === 'waiting') {
    return (
      <div style={styles.root}>
        <div style={styles.waitingBox}>
          <div style={styles.spinner} />
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginTop: 12 }}>
            Launching…
          </div>
        </div>
      </div>
    )
  }

  const hole = data?.rect
  const asset = data?.system_id
    ? `/assets/overlays/${data.system_id}.png`
    : null

  return (
    <div style={styles.root}>
      {/* Transparent hole at emulator position */}
      {hole && (
        <div style={{
          ...styles.hole,
          left: hole.x,
          top:  hole.y,
          width:  hole.w,
          height: hole.h,
        }} />
      )}

      {/* Bezel PNG — hides behind the hole via mix-blend-mode */}
      {asset && (
        <img
          src={asset}
          onLoad={() => setImgOk(true)}
          onError={() => setImgOk(false)}
          style={{
            ...styles.bezel,
            opacity: imgOk ? 1 : 0,
          }}
          alt=""
          draggable={false}
        />
      )}

      {/* CSS fallback frame when no PNG asset */}
      {(!asset || !imgOk) && hole && (
        <div style={{
          position: 'absolute', inset: 0,
          boxShadow: `inset 0 0 0 4px rgba(255,255,255,0.08)`,
          pointerEvents: 'none',
        }}>
          {/* Corner accents */}
          {[
            { top: hole.y - 2,           left: hole.x - 2 },
            { top: hole.y - 2,           left: hole.x + hole.w - 18 },
            { top: hole.y + hole.h - 18, left: hole.x - 2 },
            { top: hole.y + hole.h - 18, left: hole.x + hole.w - 18 },
          ].map((pos, i) => (
            <div key={i} style={{
              position: 'absolute', width: 20, height: 20,
              border: '2px solid rgba(255,255,255,0.25)',
              borderRadius: 2,
              ...pos,
            }} />
          ))}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    position: 'fixed',
    inset: 0,
    zIndex: 9999,
    pointerEvents: 'none',
    background: 'rgba(9,9,15,0.92)',
    isolation: 'isolate',
  },
  hole: {
    position: 'absolute',
    background: 'transparent',
    mixBlendMode: 'destination-out',
    // Force a solid color so destination-out actually punches through
    backgroundColor: 'black',
  },
  bezel: {
    position: 'absolute',
    inset: 0,
    width: '100%',
    height: '100%',
    objectFit: 'fill',
    pointerEvents: 'none',
    transition: 'opacity 0.3s ease',
  },
  waitingBox: {
    position: 'absolute',
    top: '50%', left: '50%',
    transform: 'translate(-50%, -50%)',
    display: 'flex', flexDirection: 'column', alignItems: 'center',
  },
  spinner: {
    width: 32, height: 32,
    border: '3px solid rgba(255,255,255,0.1)',
    borderTop: '3px solid rgba(255,255,255,0.5)',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
}
