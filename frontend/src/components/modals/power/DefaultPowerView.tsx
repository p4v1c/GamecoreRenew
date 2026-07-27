/**
 * The default power menu's markup — and nothing else.
 * The flow lives in PowerModal; see power/types.ts.
 */
import { motion } from 'framer-motion'
import { Overlay, OverlayLabel } from '../../ui'
import type { PowerViewProps } from './types'

export default function DefaultPowerView({
  options, focusIdx, confirmId, pendingId, scanning, scanResult,
  onActivate, onCancel,
}: PowerViewProps) {
  return (
    <Overlay onClose={onCancel} width={340}>
      <OverlayLabel text="SYSTEM" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, pointerEvents: pendingId ? 'none' : 'auto' }}>
        {options.map((o, idx) => {
          const isPending = pendingId === o.id
          const isScan = o.id === 'scan'
          const busyPulse = isPending || (isScan && scanning)
          const dimmed = pendingId !== null && !isPending
          return (
            <div key={o.id} onClick={() => onActivate(o.id)} style={{
              display: 'flex', alignItems: 'center', gap: 16, padding: '16px 18px',
              borderRadius: 14, cursor: pendingId ? 'default' : 'pointer',
              opacity: dimmed ? 0.25 : 1,
              background: isPending || idx === focusIdx
                ? `${o.color}22`
                : confirmId === o.id ? `${o.color}18` : 'rgba(255,255,255,0.04)',
              border: isPending || idx === focusIdx
                ? `1px solid ${o.color}90`
                : confirmId === o.id ? `1px solid ${o.color}70` : '1px solid rgba(255,255,255,0.07)',
              transition: 'all 0.2s',
            }}>
              <motion.div
                animate={busyPulse ? { opacity: [1, 0.35, 1] } : { opacity: 1 }}
                transition={busyPulse ? { duration: 1.1, repeat: Infinity, ease: 'easeInOut' } : undefined}
                style={{ width: 44, height: 44, borderRadius: 12, background: `${o.color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: o.color }}
              >
                {o.icon}
              </motion.div>
              <div>
                <div style={{ fontWeight: 600, fontSize: 15, color: '#fff' }}>
                  {isScan ? (scanning ? o.busy : o.label)
                          : isPending ? o.busy : confirmId === o.id ? `Confirm ${o.label}?` : o.label}
                </div>
                <div style={{ fontSize: 12, color: isScan && scanResult ? o.color : 'rgba(255,255,255,0.35)', marginTop: 2 }}>
                  {isScan && scanResult ? scanResult : o.desc}
                </div>
              </div>
            </div>
          )
        })}
        <div onClick={onCancel} style={{
          padding: '13px 18px', borderRadius: 14, cursor: pendingId ? 'default' : 'pointer',
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
