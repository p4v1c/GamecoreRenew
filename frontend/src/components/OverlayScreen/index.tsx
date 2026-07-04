import { useEffect, useState } from 'react'

interface OverlayData {
  system_id: string
  rect?: { x: number; y: number; w: number; h: number }
}

type Status = 'hidden' | 'waiting' | 'visible'

export default function OverlayScreen() {
  const [status, setStatus] = useState<Status>('hidden')
  const [data, setData]     = useState<OverlayData | null>(null)
  const [imgOk, setImgOk]   = useState(false)

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

  const hole  = data?.rect
  const asset = data?.system_id
    ? `/assets/overlays/${data.system_id}.png`
    : null

  return (
    <div style={styles.root}>
      {asset && (
        <img
          src={asset}
          onLoad={() => setImgOk(true)}
          onError={() => setImgOk(false)}
          style={{ ...styles.bezel, opacity: imgOk ? 1 : 0 }}
          alt=""
          draggable={false}
        />
      )}

      {(!asset || !imgOk) && hole && (
        <>
          <div style={{ position: 'absolute', top: 0, left: 0,            width: hole.x,                        height: '100%', background: 'rgba(9,9,15,0.95)' }} />
          <div style={{ position: 'absolute', top: 0, left: hole.x + hole.w, width: 1920 - hole.x - hole.w, height: '100%', background: 'rgba(9,9,15,0.95)' }} />
          <div style={{ position: 'absolute', top: 0,            left: hole.x, width: hole.w, height: hole.y,                background: 'rgba(9,9,15,0.95)' }} />
          <div style={{ position: 'absolute', top: hole.y + hole.h, left: hole.x, width: hole.w, height: 1080 - hole.y - hole.h, background: 'rgba(9,9,15,0.95)' }} />
        </>
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
    background: 'transparent',
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
