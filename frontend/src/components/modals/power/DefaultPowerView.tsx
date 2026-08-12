/**
 * The default power menu's markup — and nothing else.
 * The flow lives in PowerModal; see power/types.ts.
 */
import { motion } from 'framer-motion'
import { Overlay, OverlayLabel, Glyph } from '../../ui'
import type { PowerViewProps } from './types'

export default function DefaultPowerView({
  options, focusIdx, confirmId, pendingId, scanning, scanResult,
  onActivate, onCancel,
}: PowerViewProps) {
  return (
    <Overlay onClose={onCancel} width={420}>
      <OverlayLabel text="SYSTEM" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, pointerEvents: pendingId ? 'none' : 'auto' }}>
        {options.map((o, idx) => {
          const isPending = pendingId === o.id
          const isScan = o.id === 'scan'
          const busyPulse = isPending || (isScan && scanning)
          const dimmed = pendingId !== null && !isPending
          const awaiting = confirmId === o.id
          return (
            <div key={o.id} onClick={() => onActivate(o.id)} style={{
              // Not a fixed height like the settings rows: the scan result and
              // the confirmation both replace the subtitle with a longer line,
              // and clipping the answer to a mapping scan would be losing the
              // only thing the row exists to say.
              display: 'flex', alignItems: 'center', gap: 15, padding: '13px 16px',
              minHeight: 62, borderRadius: 13, cursor: pendingId ? 'default' : 'pointer',
              opacity: dimmed ? 0.25 : 1,
              background: isPending || idx === focusIdx
                ? `${o.color}22`
                : awaiting ? `${o.color}18` : 'rgba(255,255,255,0.04)',
              border: isPending || idx === focusIdx
                ? `1px solid ${o.color}90`
                : awaiting ? `1px solid ${o.color}70` : '1px solid rgba(255,255,255,0.07)',
              transition: 'all 0.2s',
            }}>
              <motion.div
                animate={busyPulse ? { opacity: [1, 0.35, 1] } : { opacity: 1 }}
                transition={busyPulse ? { duration: 1.1, repeat: Infinity, ease: 'easeInOut' } : undefined}
                style={{ flexShrink: 0, width: 38, height: 38, borderRadius: 11, background: `${o.color}20`, display: 'grid', placeItems: 'center', color: o.color }}
              >
                {/* Drawn, like every other icon in this UI. These were text
                    characters — ◎ ⌫ ⏻ ↺ ⌘ — which is a different font at a
                    different weight in each row, and ⌘ for "desktop" is a key
                    on a keyboard this box does not have. */}
                <Glyph name={o.id} size={20} />
              </motion.div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 15.5, color: awaiting ? o.color : '#fff' }}>
                  {isScan ? (scanning ? o.busy : o.label)
                          : isPending ? o.busy : awaiting ? `Confirm ${o.label}?` : o.label}
                </div>
                <div style={{ fontSize: 12.5, color: isScan && scanResult ? o.color : 'rgba(255,255,255,0.35)', marginTop: 3, lineHeight: 1.35 }}>
                  {isScan && scanResult ? scanResult
                    : awaiting ? 'Press again to go ahead — ○ cancels' : o.desc}
                </div>
              </div>
            </div>
          )
        })}
        <div onClick={onCancel} style={{
          padding: '12px 16px', borderRadius: 13, cursor: pendingId ? 'default' : 'pointer',
          background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
          color: 'rgba(255,255,255,0.4)', fontSize: 14, fontWeight: 500, textAlign: 'center', marginTop: 4,
          opacity: pendingId ? 0.25 : 1,
        }}>Cancel</div>
      </div>
      <div style={{ marginTop: 12, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        {pendingId ? ' ' : '↑↓ Navigate · ✕ Select · ○ Cancel'}
      </div>
    </Overlay>
  )
}
