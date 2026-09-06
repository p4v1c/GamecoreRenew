import { useEffect, useState } from 'react'

interface OverlayData {
  system_id: string
  rect?: { x: number; y: number; w: number; h: number }
  asset?: string | null
  source?: string
  /** The rectangle `rect` is measured in — the window the monitor forces the
   *  emulator into. Absent from an Electron main older than this field, where
   *  the box was 1080p by construction. */
  space?: { w: number; h: number }
}

/** The bezel to draw, or null for "draw nothing".
 *
 *  `asset` is resolved per game by the backend and arrives with the event.
 *  When the field is absent altogether — an Electron main process older than
 *  the resolver — fall back to the per-system path this screen used to build
 *  for itself, so an update that lands in the wrong order still shows a bezel.
 *  `null` is different from absent and means the cascade found nothing.
 */
function bezelSrc(d: OverlayData | null): string | null {
  if (!d) return null
  if (d.asset !== undefined) return d.asset
  return d.system_id ? `/assets/overlays/${d.system_id}.png` : null
}

type Status = 'hidden' | 'waiting' | 'visible'

/** The space every bezel was cut in, and what an event without one means. */
const REFERENCE = { w: 1920, h: 1080 }

/** A length in the hole's space, as a percentage of the window drawing it. */
const pct = (v: number, of: number) => `${(v / (of || 1)) * 100}%`

export default function OverlayScreen() {
  const [status, setStatus] = useState<Status>('hidden')
  const [data, setData]     = useState<OverlayData | null>(null)
  /**
   * The bezel URL that has actually loaded — not a boolean about the last event.
   *
   * `overlay:show` arrives again whenever the geometry is re-measured, and the
   * picture has no part in that: same node, same URL, nothing to load a second
   * time. Resetting a flag on every event therefore hid a bezel that was
   * already on screen — opacity 1 to 0, and the drawn black bars taking over
   * from artwork the player had been looking at — with no `load` event left to
   * come and undo it. Tied to the URL, a new measurement changes nothing and a
   * new bezel is the only thing that starts again.
   */
  const [loaded, setLoaded] = useState<string | null>(null)

  useEffect(() => {
    if (!window.gamecore) return

    window.gamecore.onOverlayShow((d: OverlayData) => {
      setData(d)
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
  const asset = bezelSrc(data)
  const imgOk = !!asset && loaded === asset
  const space = (data?.space?.w && data?.space?.h) ? data.space : REFERENCE

  return (
    <div style={styles.root}>
      {asset && (
        <img
          // Keyed on the URL: a different bezel is a different element, so the
          // `complete` check below runs for it and a stale one cannot linger.
          key={asset}
          src={asset}
          // `load` only reaches a listener that was already attached, and a
          // cached bezel can be complete before React commits the handler —
          // then nothing ever announced it and the artwork stayed invisible.
          // Reading `complete` settles that without waiting for an event.
          ref={(el) => { if (el?.complete && el.naturalWidth > 0) setLoaded(asset) }}
          onLoad={() => setLoaded(asset)}
          onError={() => setLoaded(null)}
          style={{ ...styles.bezel, opacity: imgOk ? 1 : 0 }}
          alt=""
          draggable={false}
        />
      )}

      {/* The drawn frame stands in for a bezel that exists and failed to
          load. It must NOT stand in for the absence of a bezel: a system
          nobody cut artwork for gets black bars from a hole nobody measured,
          over a game that was filling the screen correctly. `asset &&` is
          that distinction — it used to read `!asset ||`, which is the case
          that had to stop drawing. */}
      {/* In fractions of the space the hole was measured in, not in pixels of
          a screen assumed to be 1080p. The bezel image is stretched to the
          window, so the hole's position within the picture is a proportion —
          and now that the window follows the display, the bars have to be one
          too, or a 4K panel gets a frame a quarter of the way across it.
          The pair of numbers travels with the event; an older main process
          that sends none means the box it came from was 1080p. */}
      {asset && !imgOk && hole && (
        <>
          <div style={{ ...styles.bar, top: 0, bottom: 0, left: 0, width: pct(hole.x, space.w) }} />
          <div style={{ ...styles.bar, top: 0, bottom: 0, left: pct(hole.x + hole.w, space.w), right: 0 }} />
          <div style={{ ...styles.bar, top: 0, left: pct(hole.x, space.w), width: pct(hole.w, space.w), height: pct(hole.y, space.h) }} />
          <div style={{ ...styles.bar, top: pct(hole.y + hole.h, space.h), bottom: 0, left: pct(hole.x, space.w), width: pct(hole.w, space.w) }} />
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
  // The stand-in frame, drawn only when a bezel exists and failed to load.
  bar: {
    position: 'absolute',
    background: 'rgba(9,9,15,0.95)',
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
