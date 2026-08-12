import React from 'react'

// ── Colour helpers ────────────────────────────────────────────────────────────
export function hexToRgb(hex: string): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `${r},${g},${b}`
}

export function fmtTime(secs: number): string {
  if (secs <= 0) return '—'
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (h > 0 && m > 0) return `${h}h ${m}m`
  if (h > 0) return `${h}h`
  return `${m}m`
}

export function fmtDate(iso: string | null): string {
  if (!iso) return 'Never'
  const d = new Date(iso)
  const now = new Date()
  const diff = Math.floor((now.getTime() - d.getTime()) / 86400000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  if (diff < 7) return `${diff}d ago`
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

// ── Chip ──────────────────────────────────────────────────────────────────────
export function Chip({ label, color = 'rgba(255,255,255,0.1)' }: { label: string; color?: string }) {
  return (
    <span style={{
      padding: '3px 9px', borderRadius: 6,
      background: `${color}28`, border: `1px solid ${color}50`,
      fontSize: 11, fontWeight: 600, color,
    }}>{label}</span>
  )
}

// ── Toggle ────────────────────────────────────────────────────────────────────
export function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 0', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
      <span style={{ fontSize: 14, color: 'rgba(255,255,255,0.75)' }}>{label}</span>
      <div onClick={() => onChange(!value)} style={{
        width: 46, height: 25, borderRadius: 13, cursor: 'pointer',
        background: value ? 'var(--gc-accent, #7c3aed)' : 'rgba(255,255,255,0.12)',
        position: 'relative', transition: 'background 0.2s',
      }}>
        <div style={{
          position: 'absolute', top: 2.5, width: 20, height: 20,
          left: value ? 23 : 2.5, borderRadius: 10, background: '#fff',
          transition: 'left 0.2s', boxShadow: '0 1px 4px rgba(0,0,0,0.4)',
        }} />
      </div>
    </div>
  )
}

// ── Slider ────────────────────────────────────────────────────────────────────
export function SliderRow({ label, value, onChange, color = 'var(--gc-accent, #7c3aed)' }: {
  label: string; value: number; onChange: (v: number) => void; color?: string
}) {
  return (
    <div style={{ padding: '14px 0', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontSize: 14, color: 'rgba(255,255,255,0.75)' }}>{label}</span>
        <span style={{ fontSize: 13, color: 'var(--gc-accent-soft, #a78bfa)' }}>{value}%</span>
      </div>
      <input type="range" min={0} max={100} value={value} onChange={e => onChange(+e.target.value)}
        style={{ width: '100%', accentColor: color, cursor: 'pointer' }} />
    </div>
  )
}

// ── One icon set for the whole default UI ─────────────────────────────────────
/**
 * Line-drawn paths on `currentColor`, at one weight and one size.
 *
 * These were emoji, scattered across the settings screen and its pages: nine
 * glyphs from nine designers, at nine weights, in colours nothing here chose —
 * a bright orange signal meter beside a flat black circle beside a yellow
 * padlock. Update had no glyph at all, just a text arrow. Drawn as paths, they
 * take the row's colour and the theme's accent like everything else, and they
 * are the same size on every television.
 *
 * They live here rather than beside the screen that first needed them because
 * the point is that there is ONE set: a lock on the Wi-Fi list and a lock on
 * the Bluetooth list have to be the same lock.
 */
export const GLYPHS: Record<string, string> = {
  // Settings rows
  wifi:      'M5 12.5a10 10 0 0 1 14 0M8.5 16a5.5 5.5 0 0 1 7 0M12 19.5h.01',
  audio:     'M11 5 6 9H3v6h3l5 4V5zM16 9a4 4 0 0 1 0 6M19 6.5a8 8 0 0 1 0 11',
  bluetooth: 'm7 8 10 8-5 4V4l5 4-10 8',
  storage:   'M3 7a9 3 0 0 0 18 0 9 3 0 0 0-18 0v10a9 3 0 0 0 18 0V7M3 12a9 3 0 0 0 18 0',
  standby:   'M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z',
  themes:    'M12 3.5s5.5 6 5.5 9.5a5.5 5.5 0 0 1-11 0C6.5 9.5 12 3.5 12 3.5z',
  catalog:   'M4 4.5h6.5V11H4zM13.5 4.5H20V11h-6.5zM4 13h6.5v6.5H4zM13.5 13H20v6.5h-6.5z',
  bios:      'M7 7h10v10H7zM4 10h3M4 14h3M17 10h3M17 14h3M10 4v3M14 4v3M10 17v3M14 17v3',
  update:    'M12 4v11m0 0 4-4m-4 4-4-4M5 19h14',
  desktop:   'M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M16 17l5-5-5-5M21 12H9',
  // States and actions the pages need
  check:     'm5 12.5 5 5 9-11',
  lock:      'M6 10.5h12v9H6zM8.5 10.5V7a3.5 3.5 0 0 1 7 0v3.5',
  unlock:    'M6 10.5h12v9H6zM8.5 10.5V7a3.5 3.5 0 0 1 6.8-1.2',
  ethernet:  'M4 14h16v6H4zM7 17h.01M11 17h.01M15 17h.01M12 14V9M8.5 9h7V5h-7z',
  refresh:   'M20 11a8 8 0 1 0-.6 4M20 5v6h-6',
  // Restart is a loop, not a power symbol. Drawn from the same arc as `power`
  // it was a second shutdown button sitting under the first — one of them turns
  // the box off and the other does not, and the icon has to say which.
  restart:   'M3.6 12a8.4 8.4 0 1 0 2.7-6.2M3.6 4.6v4.6h4.6',
  power:     'M12 4v8M18.4 7a8 8 0 1 1-12.8 0',
  shutdown:  'M12 3.5v8.5M17.7 6.6a8 8 0 1 1-11.4 0',
  gamepad:   'M8 11h.01M6.5 9.5v3M15.5 10.5h.01M17.5 12.5h.01M7 17h10a4 4 0 0 0 4-4 4 4 0 0 0-4-4H7a4 4 0 0 0-4 4 4 4 0 0 0 4 4z',
  scan:      'M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16M12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z',
  forget:    'M5 7h14M9.5 7V5h5v2M7 7l1 13h8l1-13M10.5 11v5M13.5 11v5',
}

/**
 * `name` is looked up rather than typed as a union so a page can pass an id it
 * builds at runtime. An unknown name renders nothing — a missing icon is a gap
 * in a row, never a crash on the fallback UI.
 */
export function Glyph({ name, size = 19, width = 1.8 }: { name: string; size?: number; width?: number }) {
  const d = GLYPHS[name]
  if (!d) return null
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
      strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  )
}

// ── Signal bars (WiFi) ────────────────────────────────────────────────────────
export function Bars({ signal }: { signal: number }) {
  const filled = signal >= 80 ? 4 : signal >= 60 ? 3 : signal >= 40 ? 2 : signal >= 20 ? 1 : 0
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2 }}>
      {[1, 2, 3, 4].map(i => (
        <div key={i} style={{
          width: 3, height: 4 + i * 3, borderRadius: 1,
          background: i <= filled ? 'var(--gc-accent-soft, #a78bfa)' : 'rgba(255,255,255,0.15)',
        }} />
      ))}
    </div>
  )
}

// ── Overlay wrapper ───────────────────────────────────────────────────────────
/**
 * Every settings page brings its own Overlay, so a theme that reuses one gets a
 * full-screen fixed layer, not a fragment — it must render the page bare rather
 * than boxing it. What the theme *can* change is how that layer looks: the two
 * surfaces read CSS variables, defaulting to the values the dark UI has always
 * used. Nothing changes unless a stylesheet defines them.
 */
export function Overlay({ onClose, children, width = 480 }: {
  onClose: () => void; children: React.ReactNode; width?: number
}) {
  return (
    <div
      onClick={e => e.target === e.currentTarget && onClose()}
      style={{
        position: 'fixed', inset: 0, zIndex: 500,
        background: 'var(--gc-overlay-scrim, rgba(5,5,12,0.88))',
        backdropFilter: 'var(--gc-overlay-blur, blur(24px))',
        WebkitBackdropFilter: 'var(--gc-overlay-blur, blur(24px))',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div style={{
        background: 'var(--gc-overlay-panel, rgba(255,255,255,0.035))',
        border: '1px solid var(--gc-overlay-border, rgba(255,255,255,0.09))',
        borderRadius: 'var(--gc-overlay-radius, 20px)',
        padding: '32px 30px', width, maxWidth: '90vw',
        maxHeight: '85vh', overflowY: 'auto',
        boxShadow: '0 48px 96px rgba(0,0,0,0.9)',
      }}>
        {children}
      </div>
    </div>
  )
}

export function OverlayLabel({ text }: { text: string }) {
  return <div style={{ fontSize: 10, letterSpacing: 3, color: 'rgba(255,255,255,0.3)', marginBottom: 20, fontWeight: 700 }}>{text}</div>
}

/**
 * `right` is for a page-level action — Refresh, and nothing that the pad has to
 * reach. Rendered in the body it reads as a first list item the cursor skips;
 * on the header's line it reads as what it is.
 */
export function BackHeader({ label, onBack, right }: {
  label: string; onBack: () => void; right?: React.ReactNode
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
      <button onClick={onBack} style={{
        cursor: 'pointer', color: 'rgba(255,255,255,0.4)', fontSize: 22,
        background: 'none', border: 'none', lineHeight: 1, padding: 0,
      }}>‹</button>
      <span style={{ fontSize: 10, letterSpacing: 3, color: 'rgba(255,255,255,0.35)', fontWeight: 700 }}>{label}</span>
      {right && <div style={{ marginLeft: 'auto' }}>{right}</div>}
    </div>
  )
}
