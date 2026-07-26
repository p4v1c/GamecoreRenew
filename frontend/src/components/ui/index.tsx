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
        padding: '36px', width, maxWidth: '90vw',
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

export function BackHeader({ label, onBack }: { label: string; onBack: () => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
      <button onClick={onBack} style={{
        cursor: 'pointer', color: 'rgba(255,255,255,0.4)', fontSize: 22,
        background: 'none', border: 'none', lineHeight: 1, padding: 0,
      }}>‹</button>
      <span style={{ fontSize: 10, letterSpacing: 3, color: 'rgba(255,255,255,0.35)', fontWeight: 700 }}>{label}</span>
    </div>
  )
}
